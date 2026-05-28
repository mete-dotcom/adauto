"""
adauto HTTP server — brand standard: GET /, /health, /tools, /exec, /eval, /approve
Port: 8766  (deepstrain=8765, adauto=8766)

Every tool callable via /exec without AI.
/eval = AI agent loop powered by deepstrain.
/approve = approve/skip pending posts.
Idle timeout: auto-shutdown after N seconds of inactivity.
"""
from __future__ import annotations

import json
import os
import threading
import time as _time
import uuid as _uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

from .db import (
    init_db, get_stats, get_queued, get_pending_approval, get_approved,
    approve_post, skip_post, update_post_body, add_post,
)
from .config import list_campaigns, load_campaign, CAMPAIGNS_DIR
from . import __version__

DEFAULT_PORT = 8766
DEFAULT_IDLE_TIMEOUT = 1800  # 30 min

# ── TOOLS registry ────────────────────────────────────────────────────────────

TOOLS = {
    "list_campaigns": {
        "description": "List all available campaigns",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    "get_stats": {
        "description": "Get posting statistics per platform/status",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    "get_pending_approval": {
        "description": "Get posts waiting for user approval",
        "input_schema": {
            "type": "object",
            "properties": {
                "campaign": {"type": "string"},
                "platform": {"type": "string"},
            },
            "required": [],
        },
    },
    "get_approved": {
        "description": "Get approved posts ready to publish",
        "input_schema": {
            "type": "object",
            "properties": {"platform": {"type": "string"}},
            "required": [],
        },
    },
    "approve_post": {
        "description": "Approve a pending post (by ID)",
        "input_schema": {
            "type": "object",
            "properties": {"post_id": {"type": "integer"}},
            "required": ["post_id"],
        },
    },
    "skip_post": {
        "description": "Skip/reject a pending post (by ID)",
        "input_schema": {
            "type": "object",
            "properties": {"post_id": {"type": "integer"}},
            "required": ["post_id"],
        },
    },
    "generate_post": {
        "description": "Generate a post for a campaign+platform via deepstrain",
        "input_schema": {
            "type": "object",
            "properties": {
                "campaign": {"type": "string"},
                "platform": {"type": "string"},
                "post_type": {"type": "string", "enum": ["showcase", "tutorial", "question", "comparison", "update"]},
                "extra_context": {"type": "string"},
            },
            "required": ["campaign", "platform"],
        },
    },
    "run_campaign": {
        "description": "Publish all approved posts for a campaign",
        "input_schema": {
            "type": "object",
            "properties": {
                "campaign": {"type": "string"},
                "platform": {"type": "string"},
                "dry_run": {"type": "boolean"},
            },
            "required": ["campaign"],
        },
    },
    "check_engagement": {
        "description": "Poll platforms for upvotes/comments on recent posts",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    "score_styles": {
        "description": "Show performance scores per post type (learning data)",
        "input_schema": {
            "type": "object",
            "properties": {"campaign": {"type": "string"}},
            "required": [],
        },
    },
}


# ── Tool executor ─────────────────────────────────────────────────────────────

def _exec_tool(name: str, args: dict) -> Any:
    """Execute a tool by name and return result."""

    if name == "list_campaigns":
        names = list_campaigns()
        campaigns = []
        for n in names:
            c = load_campaign(n)
            if c:
                campaigns.append({
                    "name": c.name,
                    "product": c.product,
                    "enabled": c.enabled,
                    "platforms": [p.name for p in c.platforms],
                })
        return {"campaigns": campaigns}

    elif name == "get_stats":
        return get_stats()

    elif name == "get_pending_approval":
        posts = get_pending_approval(
            campaign_name=args.get("campaign"),
            platform=args.get("platform"),
        )
        return {"pending": posts, "count": len(posts)}

    elif name == "get_approved":
        posts = get_approved(platform=args.get("platform"))
        return {"approved": posts, "count": len(posts)}

    elif name == "approve_post":
        post_id = args.get("post_id")
        if post_id is None:
            return {"error": "post_id required"}
        approve_post(int(post_id))
        return {"ok": True, "post_id": post_id}

    elif name == "skip_post":
        post_id = args.get("post_id")
        if post_id is None:
            return {"error": "post_id required"}
        skip_post(int(post_id))
        return {"ok": True, "post_id": post_id}

    elif name == "generate_post":
        campaign_name = args.get("campaign")
        platform = args.get("platform")
        if not campaign_name or not platform:
            return {"error": "campaign and platform required"}
        camp = load_campaign(campaign_name)
        if not camp:
            return {"error": f"Campaign not found: {campaign_name}"}
        from .generator import generate_post
        post = generate_post(
            camp, platform,
            post_type=args.get("post_type", "showcase"),
            extra_context=args.get("extra_context", ""),
            ds_url=camp.deepstrain_url,
        )
        if post:
            # Save to DB as pending_approval
            post_id = add_post(
                campaign_name=campaign_name,
                platform=platform,
                post_type=post.get("post_type", "showcase"),
                title=post.get("title", ""),
                body=post.get("body", ""),
            )
            post["post_id"] = post_id
            post["status"] = "pending_approval"
            post["note"] = f"Review with `adauto review` or POST /approve {{\"post_id\": {post_id}}}"
        return post or {"error": "generation failed"}

    elif name == "run_campaign":
        campaign_name = args.get("campaign")
        if not campaign_name:
            return {"error": "campaign required"}
        camp = load_campaign(campaign_name)
        if not camp:
            return {"error": f"Campaign not found: {campaign_name}"}
        platform_filter = args.get("platform")
        dry_run = args.get("dry_run", False)

        # Only publish approved posts
        approved = get_approved(platform=platform_filter)
        if not approved:
            return {"ok": True, "note": "No approved posts to publish. Generate and approve posts first.", "published": 0}

        from .platforms.reddit import RedditPoster
        from .platforms.devto import DevtoPoster
        from .platforms.twitter import TwitterPoster
        from .scheduler import record_run

        results = {"published": [], "failed": [], "dry_run": dry_run}
        by_platform: dict[str, list] = {}
        for p in approved:
            if p["campaign_name"] != campaign_name:
                continue
            by_platform.setdefault(p["platform"], []).append(p)

        for plat_name, posts in by_platform.items():
            plat = camp.get_platform(plat_name)
            if not plat:
                continue
            try:
                if plat_name == "reddit" and not dry_run:
                    poster = RedditPoster()
                    for post in posts:
                        url = poster.post(camp, plat, post,
                                         subreddit=(plat.subreddits or ["programming"])[0])
                        if url:
                            results["published"].append({"id": post["id"], "url": url})
                        else:
                            results["failed"].append(post["id"])
                elif dry_run:
                    for post in posts:
                        results["published"].append({"id": post["id"], "dry_run": True,
                                                     "title": post.get("title", "")[:60]})
                record_run(campaign_name, plat_name)
            except Exception as e:
                results["failed"].append({"platform": plat_name, "error": str(e)})

        return results

    elif name == "check_engagement":
        from .analytics import check_engagement_all
        updated = check_engagement_all()
        return {"updated": updated}

    elif name == "score_styles":
        from .analytics import score_styles
        scores = score_styles(campaign_name=args.get("campaign"))
        return {"scores": scores}

    else:
        return {"error": f"Unknown tool: {name}"}


# ── Plan-first for /eval ──────────────────────────────────────────────────────

_pending_plans: dict = {}

_PLAN_SYSTEM = (
    "You are adauto's planning agent. "
    "The user wants to automate developer marketing. "
    "Your job: create a numbered step-by-step plan. "
    "DO NOT execute steps — only plan. "
    "Each step must be a concrete action (generate, review, approve, post, check-engagement). "
    "No code, no tool calls. Plain numbered list only."
)


def _is_complex(prompt: str) -> bool:
    keywords = ["generate", "create", "run", "post", "campaign", "all platforms",
                 "schedule", "approve", "publish", "benchmark"]
    prompt_lower = prompt.lower()
    hits = sum(1 for kw in keywords if kw in prompt_lower)
    return len(prompt) > 120 or hits >= 2


def _eval_agent(prompt: str, max_turns: int, ds_url: str) -> dict:
    """Simple agent loop: calls deepstrain for reasoning, executes tools."""
    import requests

    system = (
        "You are adauto, a developer marketing automation agent. "
        "You have these tools available via JSON tool calls:\n"
        + json.dumps(TOOLS, indent=2)
        + "\n\nTo call a tool, respond with:\n"
        "TOOL: <tool_name>\nARGS: <json args>\n\n"
        "When done, respond with: ANSWER: <your final message>"
    )

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": prompt},
    ]

    for turn in range(max_turns):
        try:
            resp = requests.post(
                f"{ds_url}/eval",
                json={"prompt": "\n".join(
                    f"{m['role'].upper()}: {m['content']}" for m in messages[-4:]
                ),
                      "plan_first": False, "max_turns": 2},
                timeout=60,
            )
            resp.raise_for_status()
            answer = resp.json().get("answer", "")
        except Exception as e:
            return {"error": str(e), "turns": turn}

        if "ANSWER:" in answer:
            final = answer.split("ANSWER:", 1)[1].strip()
            return {"answer": final, "turns": turn + 1}

        if "TOOL:" in answer:
            import re
            m = re.search(r'TOOL:\s*(\w+)\s*\nARGS:\s*(\{.*?\})', answer, re.DOTALL)
            if m:
                tool_name = m.group(1)
                try:
                    tool_args = json.loads(m.group(2))
                except Exception:
                    tool_args = {}
                result = _exec_tool(tool_name, tool_args)
                messages.append({"role": "assistant", "content": answer})
                messages.append({"role": "user", "content": f"TOOL_RESULT: {json.dumps(result)}"})
                continue

        # No structured response — treat as final answer
        return {"answer": answer, "turns": turn + 1}

    return {"error": "max_turns reached", "turns": max_turns}


# ── HTTP Handler ──────────────────────────────────────────────────────────────

class AdautoHandler(BaseHTTPRequestHandler):

    _last_request: list  # set by make_server()
    _ds_url: str

    def log_message(self, fmt, *args):
        pass  # suppress default access log

    def _send_json(self, status: int, data: dict) -> None:
        body = json.dumps(data, ensure_ascii=False, indent=2).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length))
        except Exception:
            return {}

    def _touch(self):
        self._last_request[0] = _time.monotonic()

    # ── GET ──────────────────────────────────────────────────────────────────

    def do_GET(self):
        self._touch()

        if self.path == "/" or self.path == "":
            campaigns = list_campaigns()
            self._send_json(200, {
                "name": "adauto",
                "version": __version__,
                "description": (
                    "adauto is a developer marketing automation agent. "
                    "Generates platform-specific posts using deepstrain, "
                    "tracks engagement, learns from results, and adapts. "
                    "User approval required before any post goes live."
                ),
                "port": DEFAULT_PORT,
                "campaigns": campaigns,
                "endpoints": {
                    "GET  /":                "This self-description",
                    "GET  /health":          "Liveness probe",
                    "GET  /tools":           "All tools with schemas",
                    "POST /exec":            '{"tool": "<name>", "args": {...}}',
                    "POST /eval":            '{"prompt": "<task>", "plan_first": "auto"}',
                    "POST /approve":         '{"post_id": N}  or  {"approve_all": true}',
                    "POST /skip":            '{"post_id": N}',
                },
                "workflow": [
                    "1. POST /exec {tool:'generate_post', args:{campaign, platform}} → pending_approval",
                    "2. GET /exec {tool:'get_pending_approval'} → review posts",
                    "3. POST /approve {post_id: N} → approved",
                    "4. POST /exec {tool:'run_campaign', args:{campaign}} → published",
                    "5. POST /exec {tool:'check_engagement'} → learning data updated",
                ],
                "learning": "adauto tracks upvotes/comments per post style and injects top examples into future prompts",
                "idle_timeout": getattr(self.server, "_idle_timeout", DEFAULT_IDLE_TIMEOUT),
            })

        elif self.path == "/health":
            self._send_json(200, {
                "status": "ok",
                "version": __version__,
                "campaigns": len(list_campaigns()),
                "pending_approval": len(get_pending_approval()),
                "approved_ready": len(get_approved()),
            })

        elif self.path == "/tools":
            self._send_json(200, {
                "tools": [
                    {"name": k, **v} for k, v in TOOLS.items()
                ]
            })

        else:
            self._send_json(404, {"error": "not found"})

    # ── POST ─────────────────────────────────────────────────────────────────

    def do_POST(self):
        self._touch()
        body = self._read_body()

        if self.path == "/exec":
            tool = body.get("tool", "")
            args = body.get("args", {})
            if not tool:
                return self._send_json(400, {"error": "tool required"})
            result = _exec_tool(tool, args)
            self._send_json(200, {"tool": tool, "result": result})

        elif self.path == "/eval":
            prompt    = body.get("prompt", "")
            plan_id   = body.get("plan_id", "").strip()
            approved  = body.get("approved", False)
            plan_mode = body.get("plan_first", "auto")
            ds_url    = body.get("ds_url", self._ds_url)
            max_turns = int(body.get("max_turns", 6))

            if not prompt and not plan_id:
                return self._send_json(400, {"error": "prompt required"})

            # Execute approved plan
            if plan_id and approved:
                entry = _pending_plans.pop(plan_id, None)
                if not entry:
                    return self._send_json(404, {"error": "plan_id not found"})
                exec_prompt = (
                    f"APPROVED PLAN (execute each step):\n{entry['plan']}\n\n"
                    f"Original task: {entry['prompt']}"
                )
                result = _eval_agent(exec_prompt, max_turns, ds_url)
                result["plan_executed"] = plan_id
                return self._send_json(200, result)

            # Plan-first phase
            do_plan = (plan_mode is True or plan_mode == "true") or \
                      (plan_mode == "auto" and _is_complex(prompt))

            if do_plan:
                import requests
                try:
                    resp = requests.post(
                        f"{ds_url}/eval",
                        json={"prompt": f"{_PLAN_SYSTEM}\n\nTask: {prompt}",
                              "plan_first": False, "max_turns": 3},
                        timeout=60,
                    )
                    resp.raise_for_status()
                    plan_text = resp.json().get("answer", "")
                except Exception as e:
                    return self._send_json(500, {"error": f"planning failed: {e}"})

                pid = str(_uuid.uuid4())[:8]
                _pending_plans[pid] = {"prompt": prompt, "plan": plan_text}
                return self._send_json(200, {
                    "status": "plan_ready",
                    "plan": plan_text,
                    "plan_id": pid,
                    "note": f"Review the plan. Execute: POST /eval {{\"plan_id\":\"{pid}\",\"approved\":true}}",
                })

            # Direct execution
            result = _eval_agent(prompt, max_turns, ds_url)
            return self._send_json(200, result)

        elif self.path == "/approve":
            post_id = body.get("post_id")
            approve_all = body.get("approve_all", False)

            if approve_all:
                pending = get_pending_approval(
                    campaign_name=body.get("campaign"),
                    platform=body.get("platform"),
                )
                for p in pending:
                    approve_post(p["id"])
                return self._send_json(200, {"ok": True, "approved_count": len(pending)})

            if post_id is None:
                return self._send_json(400, {"error": "post_id or approve_all required"})
            approve_post(int(post_id))
            return self._send_json(200, {"ok": True, "post_id": post_id})

        elif self.path == "/skip":
            post_id = body.get("post_id")
            if post_id is None:
                return self._send_json(400, {"error": "post_id required"})
            skip_post(int(post_id))
            return self._send_json(200, {"ok": True, "post_id": post_id})

        else:
            self._send_json(404, {"error": "not found"})


# ── Server factory ────────────────────────────────────────────────────────────

def make_server(host: str = "0.0.0.0", port: int = DEFAULT_PORT,
                idle_timeout: int = DEFAULT_IDLE_TIMEOUT,
                ds_url: str = "http://localhost:8765") -> HTTPServer:
    init_db()

    last_request = [_time.monotonic()]

    # Inject shared state into handler class
    class _Handler(AdautoHandler):
        _last_request = last_request
        _ds_url = ds_url

    server = HTTPServer((host, port), _Handler)
    server._idle_timeout = idle_timeout

    # Idle watchdog thread
    def _watchdog():
        while True:
            _time.sleep(30)
            elapsed = _time.monotonic() - last_request[0]
            if elapsed >= idle_timeout:
                print(f"[adauto] idle {elapsed:.0f}s — shutting down (OS service will restart)")
                server.shutdown()
                return

    t = threading.Thread(target=_watchdog, daemon=True)
    t.start()

    return server


def run_server(host: str = "0.0.0.0", port: int = DEFAULT_PORT,
               idle_timeout: int = DEFAULT_IDLE_TIMEOUT,
               ds_url: str = "http://localhost:8765") -> None:
    server = make_server(host, port, idle_timeout, ds_url)
    print(f"[adauto] serving on http://{host}:{port}  (idle timeout: {idle_timeout}s)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
