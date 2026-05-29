"""
adauto responder — craft genuine help responses and queue them for posting.

Design:
  1. Pain match → template response (zero LLM, always works)
  2. Optional deepstrain enrichment → personalized to the specific thread
  3. Ethics gate (layer 1 + 2) before anything is queued
  4. Human approval via `adauto review` — nothing posts automatically

The response is helpful FIRST. Product mention is natural, brief, one sentence.
If the person doesn't need the product, the response still helps them.
This is the line between genuine help and spam.
"""
from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .pain_detector import PainMatch
    from .signal_store import Signal


@dataclass
class DraftResponse:
    signal_url: str
    platform: str
    title: str          # original post title (context)
    body: str           # the response to post
    product: str        # which product is referenced
    pain_pattern: str   # pattern_id that triggered this
    confidence: float
    enriched: bool = False


def _enrich_with_brain(template: str, pain: "PainMatch",
                       post_title: str, post_body_snip: str,
                       ds_url: str = "http://localhost:8765",
                       timeout: int = 60) -> str:
    """
    Optional: ask deepstrain to personalise the template to the specific thread.
    Falls back to the template if the brain is unreachable (immortality rule).
    """
    prompt = (
        f"You are helping a developer on a forum. Personalise this response to "
        f"their specific situation. Keep it concise (3–5 sentences). "
        f"The product mention must stay but must feel natural and helpful. "
        f"Never start with 'I' or sound like a bot.\n\n"
        f"THREAD TITLE: {post_title}\n"
        f"THREAD SNIPPET: {post_body_snip[:300]}\n\n"
        f"TEMPLATE RESPONSE:\n{template}\n\n"
        f"PERSONALISED RESPONSE (keep the same structure, just tailor the opening):"
    )
    try:
        body = json.dumps({"prompt": prompt, "max_turns": 2}).encode()
        req = urllib.request.Request(
            ds_url.rstrip("/") + "/eval", data=body,
            headers={"Content-Type": "application/json"}, method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            answer = json.loads(r.read()).get("answer", "").strip()
        if len(answer) > 80:
            return answer
    except Exception:
        pass
    return template


def build_response(signal_row: dict, pain: "PainMatch",
                   ds_url: str = "http://localhost:8765",
                   use_brain: bool = True) -> DraftResponse:
    """
    Build a draft response for a signal given its pain match.
    Optionally enriches with deepstrain for personalisation.
    """
    body = pain.response_template
    enriched = False
    if use_brain:
        enriched_body = _enrich_with_brain(
            body, pain,
            signal_row.get("title", ""),
            signal_row.get("body_snip", ""),
            ds_url=ds_url,
        )
        if enriched_body != body:
            body = enriched_body
            enriched = True

    return DraftResponse(
        signal_url=signal_row["signal_url"],
        platform=signal_row["platform"],
        title=signal_row.get("title", ""),
        body=body,
        product=pain.product,
        pain_pattern=pain.pattern_id,
        confidence=pain.confidence,
        enriched=enriched,
    )


def queue_as_post(draft: DraftResponse, campaign_name: str,
                  db_add_post_fn) -> int | None:
    """
    Push the draft response through the normal adauto post pipeline:
    ethics gate → pending_approval → `adauto review` → `adauto post`.

    Returns the post DB id (or None if blocked by ethics).
    """
    from .ethics import check as ethics_check

    title = f"Response to: {draft.title[:80]}"
    result = ethics_check(
        title=title,
        body=draft.body,
        campaign_name=campaign_name,
        platform=draft.platform,
    )
    if not result.allowed:
        return None  # ethics blocked — never queue

    return db_add_post_fn(
        campaign_name=campaign_name,
        platform=draft.platform,
        post_type="comment",
        title=title,
        body=draft.body,
    )


def scan_and_queue(campaign_name: str,
                   min_confidence: float = 0.5,
                   ds_url: str = "http://localhost:8765",
                   use_brain: bool = True,
                   verbose: bool = False) -> dict:
    """
    Full respond cycle:
      1. Load new signals from store
      2. Run pain_detector on each
      3. Build + ethics-check draft response
      4. Queue as pending_approval post (waits for `adauto review`)
    Returns {scanned, pain_found, queued, blocked}.
    """
    from . import signal_store as ss
    from .db import add_post
    from .pain_detector import detect_pain

    signals = ss.get_new(campaign_name, limit=100)
    scanned = len(signals)
    pain_found = queued = blocked = 0

    for sig in signals:
        combined = f"{sig.get('title','')} {sig.get('body_snip','')}"
        matches = detect_pain(sig.get("title", ""), sig.get("body_snip", ""))
        if not matches or matches[0].confidence < min_confidence:
            continue
        pain_found += 1
        best = matches[0]

        if verbose:
            print(f"  [{sig['platform']:6}] pain={best.pattern_id} "
                  f"conf={best.confidence:.0%}  {sig.get('title','')[:55]}")

        draft = build_response(sig, best, ds_url=ds_url, use_brain=use_brain)
        pid = queue_as_post(draft, campaign_name, add_post)
        if pid is not None:
            queued += 1
            ss.mark(sig["id"], "acted")
        else:
            blocked += 1

    return {"scanned": scanned, "pain_found": pain_found,
            "queued": queued, "blocked_by_ethics": blocked}
