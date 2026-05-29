"""Content generator — uses deepstrain /eval to write platform-ready posts."""
import json
import time
import requests
from typing import Optional

from .config import Campaign, Platform
from .crash import retry, log, guard

# Default deepstrain URL (can be overridden per campaign)
DEFAULT_DS_URL = "http://localhost:8765"

_SYSTEM_CONTEXT = """You are an expert developer marketing copywriter.
Write authentic, helpful posts for developer communities — NOT spammy ads.
- Be specific: mention real features, real commands, real use-cases
- Show, don't tell: use code snippets when relevant
- Fit the platform tone exactly
- Never start with "I" or "Hey"
- Never use 🚀🔥💯 unless the platform explicitly encourages emoji (Twitter/X)
"""

_PLATFORM_TONES = {
    "reddit": "Conversational, self-aware, code-heavy. Reddit hates obvious ads — frame as sharing something cool or asking for feedback.",
    "twitter": "Short, punchy, code snippet or screenshot hook. 1-3 hashtags max.",
    "devto": "Tutorial-style or opinion piece. Markdown. Real depth, not fluff.",
    "hackernews": "Minimal, technical, no hype words. Title: 'Show HN: ...' or just a plain statement.",
    "linkedin": "Professional tone, 1 paragraph hook, bullet points, mild CTA.",
}

_POST_TYPE_INSTRUCTIONS = {
    "showcase": "Showcase what the tool does with a concrete example. Lead with the problem it solves.",
    "tutorial": "Step-by-step: install → configure → run → see result. Include code blocks.",
    "question": "Ask the community a genuine question that relates to the tool's use-case. Subtle mention only.",
    "comparison": "Compare approach/result with/without the tool. Quantify if possible.",
    "update": "Announce a new feature. What changed, why it matters, how to upgrade.",
}


def _build_prompt(campaign: Campaign, platform: str, post_type: str,
                  extra_context: str = "") -> str:
    tone = _PLATFORM_TONES.get(platform, "Professional and technical.")
    ptype_instr = _POST_TYPE_INSTRUCTIONS.get(post_type, "Write a relevant post about the tool.")

    # Adaptive learning: inject what's worked before
    learning_ctx = ""
    try:
        from .analytics import build_learning_context
        learning_ctx = build_learning_context(campaign.name, platform, post_type)
    except Exception:
        pass

    return f"""IMPORTANT: This is a pure text generation task. Do NOT use any tools, do NOT search files, do NOT run commands. Just write the content directly.

{_SYSTEM_CONTEXT}

CAMPAIGN:
- Product: {campaign.product}
- Tagline: {campaign.tagline}
- Install: `{campaign.install_cmd}`
- Repo: {campaign.repo_url}
- Site: {campaign.site_url}

TARGET PLATFORM: {platform}
Platform tone: {tone}

POST TYPE: {post_type}
Instructions: {ptype_instr}

{f'EXTRA CONTEXT: {extra_context}' if extra_context else ''}
{learning_ctx}

Write ONE post for this platform. Return a JSON object with these keys:
- "title": post title (null if platform doesn't use titles, e.g. Twitter)
- "body": full post body (markdown ok for reddit/devto)
- "tags": list of relevant tags/subreddit suggestions (max 5)
- "estimated_chars": character count of body

Return ONLY the JSON, no explanation."""


@retry(max=3, delay=3.0, backoff=2.0, label="deepstrain /eval")
def _call_deepstrain(ds_url: str, payload: dict) -> dict:
    """POST to deepstrain /eval with retry on transient network errors."""
    resp = requests.post(f"{ds_url}/eval", json=payload, timeout=120)
    resp.raise_for_status()
    return resp.json()


def generate_post(campaign: Campaign, platform: str, post_type: str,
                  extra_context: str = "", ds_url: str = None,
                  max_turns: int = 6) -> Optional[dict]:
    """
    Generate a platform-ready post via deepstrain /eval.
    Returns dict with title, body, tags or None on failure.
    Retries up to 3× on network errors before giving up.
    """
    ds_url = ds_url or campaign.deepstrain_url or DEFAULT_DS_URL
    prompt = _build_prompt(campaign, platform, post_type, extra_context)

    try:
        data = _call_deepstrain(
            ds_url,
            {
                "prompt": prompt,
                "plan_first": False,   # content gen = single turn, no plan needed
                "max_turns": max_turns,
            },
        )
    except Exception as e:
        log.error("[generator] deepstrain /eval failed after retries: %s", e)
        print(f"[generator] deepstrain unreachable — is `deepstrain serve` running on {ds_url}?")
        return None

    # Check for hard errors
    if "error" in data and not data.get("answer"):
        log.warning("[generator] deepstrain error: %s", data["error"])
        print(f"[generator] deepstrain error: {data['error']}")
        return None

    # Extract final answer from agent result
    # deepstrain returns: {"answer": "...", "turns": N, ...}
    result_text = (data.get("answer") or data.get("result")
                   or data.get("content") or "")
    if not result_text and isinstance(data.get("messages"), list):
        # last assistant message
        for m in reversed(data["messages"]):
            if m.get("role") == "assistant" and m.get("content"):
                result_text = m["content"]
                break

    if not result_text:
        print(f"[generator] empty result from deepstrain")
        return None

    # Parse JSON from result (might be wrapped in markdown code block)
    result_text = result_text.strip()
    if result_text.startswith("```"):
        lines = result_text.splitlines()
        # strip ```json ... ``` wrapper
        inner = []
        in_block = False
        for ln in lines:
            if ln.startswith("```") and not in_block:
                in_block = True
                continue
            if ln.startswith("```") and in_block:
                break
            if in_block:
                inner.append(ln)
        result_text = "\n".join(inner)

    import re

    def _try_parse(text: str) -> Optional[dict]:
        """Try to parse a JSON object from text, handling common LLM quirks."""
        text = text.strip()
        # Direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        # Strip markdown code fence
        if text.startswith("```"):
            inner = re.sub(r'^```[^\n]*\n', '', text)
            inner = re.sub(r'\n```$', '', inner).strip()
            try:
                return json.loads(inner)
            except json.JSONDecodeError:
                pass
        # Find first balanced { ... } block
        start = text.find('{')
        if start != -1:
            depth = 0
            for i, ch in enumerate(text[start:], start):
                if ch == '{':
                    depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(text[start:i+1])
                        except json.JSONDecodeError:
                            break
        return None

    post = _try_parse(result_text)

    if post is None:
        # Fallback: treat the whole answer as body text, extract title from first line
        lines = result_text.strip().splitlines()
        title = None
        body = result_text.strip()
        # Try to find a bold title like **Title:** or # Title
        for ln in lines[:5]:
            m = re.match(r'^(?:\*\*Title:\*\*|##+)\s*(.+)', ln.strip())
            if m:
                title = m.group(1).strip('*').strip()
                body = "\n".join(lines[lines.index(ln)+1:]).strip()
                break
        if title is None and lines:
            # first non-empty line as title if it looks like a title
            first = lines[0].strip().strip('*#').strip()
            if len(first) < 120 and not first.endswith('.'):
                title = first
                body = "\n".join(lines[1:]).strip()
        post = {"title": title, "body": body, "tags": [], "estimated_chars": len(body)}
        print(f"[generator] used text fallback — title: {title}")

    # Normalize
    post.setdefault("title", None)
    post.setdefault("body", "")
    post.setdefault("tags", [])
    post.setdefault("estimated_chars", len(post.get("body", "")))
    return post


def generate_batch(campaign: Campaign, platform_name: str, count: int = 3,
                   post_types: list = None, ds_url: str = None) -> list[dict]:
    """Generate `count` posts for a platform, cycling through post_types."""
    plat = campaign.get_platform(platform_name)
    if not plat:
        print(f"[generator] platform {platform_name!r} not found in campaign")
        return []

    types = post_types or plat.post_types or ["showcase"]
    results = []
    for i in range(count):
        ptype = types[i % len(types)]
        print(f"[generator] generating {platform_name}/{ptype} ({i+1}/{count})...")
        post = generate_post(campaign, platform_name, ptype, ds_url=ds_url)
        if post:
            post["post_type"] = ptype
            post["platform"] = platform_name
            results.append(post)
        time.sleep(1)  # small rate limit between calls
    return results
