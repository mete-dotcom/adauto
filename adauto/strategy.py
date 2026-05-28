"""
Strategy engine — adauto's core algorithm.

Decides: which platform, which post_type, which subreddit, at what cost.
LLMs never need to make these decisions. adauto handles it internally.

Algorithm: exploit/explore balance
  - If ≥2 posts with data → exploit best performing (post_type × platform)
  - If new combination → explore (try untried types first)
  - Subreddit selection → skip those on cooldown
  - Cost tracking → tokens per post, score per token (ROI)

All decisions are deterministic, logged, and explainable.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

# DeepSeek API pricing (USD per 1M tokens, as of 2025)
# Cache hit / cache miss pricing
DEEPSEEK_INPUT_COST_PER_1M  = 0.14   # $0.14 / 1M input tokens (cache miss)
DEEPSEEK_OUTPUT_COST_PER_1M = 0.28   # $0.28 / 1M output tokens
AVG_TOKENS_PER_POST         = 1800   # ~1200 input + 600 output per generation


@dataclass
class StrategyDecision:
    platform: str
    post_type: str
    subreddit: Optional[str]       # reddit only
    mode: str                      # "exploit" | "explore" | "default"
    confidence: float              # 0-1
    reason: str
    estimated_tokens: int = AVG_TOKENS_PER_POST
    estimated_cost_usd: float = field(init=False)
    expected_score: float = 0.0    # predicted engagement score (0 = unknown)

    def __post_init__(self):
        input_tokens  = int(self.estimated_tokens * 0.67)
        output_tokens = int(self.estimated_tokens * 0.33)
        self.estimated_cost_usd = (
            input_tokens  / 1_000_000 * DEEPSEEK_INPUT_COST_PER_1M +
            output_tokens / 1_000_000 * DEEPSEEK_OUTPUT_COST_PER_1M
        )

    @property
    def cost_per_expected_score(self) -> Optional[float]:
        if self.expected_score > 0:
            return round(self.estimated_cost_usd / self.expected_score, 6)
        return None

    def summary(self) -> str:
        roi = f" | ROI: ${self.cost_per_expected_score:.5f}/score" if self.expected_score else ""
        sub = f" r/{self.subreddit}" if self.subreddit else ""
        return (f"{self.platform}{sub} [{self.post_type}] "
                f"{self.mode} conf={self.confidence:.0%} "
                f"~${self.estimated_cost_usd:.5f}{roi}")


def select_strategy(campaign) -> list[StrategyDecision]:
    """
    For each platform that is due, decide the optimal post type and target.
    Returns a list of StrategyDecisions (one per due platform).

    Called by `run` tool — LLMs never call this directly.
    """
    from .scheduler import due_platforms
    from .analytics import score_styles, best_examples

    due = due_platforms(campaign)
    if not due:
        return []

    # Load all scores for this campaign
    all_scores = score_styles(campaign.name)

    decisions = []
    for plat in due:
        plat_scores = [
            s for s in all_scores
            if s["platform"] == plat.name and s["n_posts"] >= 2
        ]

        # --- Post type selection ---
        if plat_scores:
            # Exploit: use the best historically performing type
            best = plat_scores[0]
            post_type  = best["post_type"]
            mode       = "exploit"
            confidence = min(0.95, 0.5 + best["n_posts"] * 0.05)
            expected   = best["total_score"] / best["n_posts"]
            reason     = (
                f"Best historically: {post_type} ({best['n_posts']} posts, "
                f"avg {best['avg_upvotes']:.0f}↑ {best['avg_comments']:.0f}💬)"
            )
        else:
            # Explore: try post types we haven't used yet
            tried = {s["post_type"] for s in all_scores if s["platform"] == plat.name}
            all_types = set(plat.post_types)
            untried   = list(all_types - tried)

            if untried:
                # Prefer types that work on other platforms
                cross_best = [
                    s["post_type"] for s in all_scores
                    if s["post_type"] in untried
                ]
                post_type = cross_best[0] if cross_best else untried[0]
                mode = "explore"
                confidence = 0.3
                reason = f"Exploring new type (untried on {plat.name})"
            else:
                post_type  = plat.post_types[0] if plat.post_types else "showcase"
                mode       = "default"
                confidence = 0.2
                reason     = "No historical data, using default"
            expected = 0.0

        # --- Subreddit selection (Reddit only) ---
        subreddit = None
        if plat.name == "reddit":
            subreddit = _pick_subreddit(campaign.name, plat)

        decisions.append(StrategyDecision(
            platform=plat.name,
            post_type=post_type,
            subreddit=subreddit,
            mode=mode,
            confidence=confidence,
            reason=reason,
            expected_score=expected,
        ))

    return decisions


def _pick_subreddit(campaign_name: str, platform) -> Optional[str]:
    """Pick the best available subreddit (not on cooldown, best ROI first)."""
    from .analytics import score_styles
    from .db import get_conn

    # Check cooldowns
    available = []
    for sub in (platform.subreddits or []):
        from .db import kv_get
        from datetime import datetime, timezone, timedelta
        key = f"reddit_cooldown:{campaign_name}:{sub}"
        last_str = kv_get(key)
        if not last_str:
            available.append(sub)
            continue
        last = datetime.fromisoformat(last_str)
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        elapsed = datetime.now(timezone.utc) - last
        if elapsed >= timedelta(hours=platform.cooldown_hours):
            available.append(sub)

    if not available:
        return None

    # Score subreddits by historical performance
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT url, upvotes, comments FROM posts
               WHERE campaign_name=? AND platform='reddit' AND status='posted'
               AND url IS NOT NULL""",
            (campaign_name,),
        ).fetchall()

    sub_scores: dict[str, list[float]] = {}
    for r in rows:
        url = r["url"] or ""
        for sub in available:
            if f"/r/{sub}/" in url:
                score = (r["upvotes"] or 0) + 3 * (r["comments"] or 0)
                sub_scores.setdefault(sub, []).append(float(score))

    # Sort available by avg score, put new ones first (explore)
    def _avg(sub):
        scores = sub_scores.get(sub, [])
        if not scores:
            return 9999  # unexplored = highest priority (explore first)
        return sum(scores) / len(scores)

    return sorted(available, key=_avg, reverse=True)[0]


# ── Cost tracking ─────────────────────────────────────────────────────────────

def record_generation_cost(post_id: int, tokens_used: int) -> None:
    """Record actual token cost for a generated post."""
    from .db import get_conn
    cost = (
        tokens_used * 0.67 / 1_000_000 * DEEPSEEK_INPUT_COST_PER_1M +
        tokens_used * 0.33 / 1_000_000 * DEEPSEEK_OUTPUT_COST_PER_1M
    )
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO kv (key, value) VALUES (?, ?)",
            (f"post_cost:{post_id}", str(cost))
        )


def get_campaign_roi(campaign_name: str) -> dict:
    """
    Compute ROI for a campaign:
    - Total estimated generation cost
    - Total engagement score earned
    - Cost per engagement point
    - Best performing post_type × platform
    """
    from .analytics import score_styles
    from .db import get_conn

    scores = score_styles(campaign_name)

    # Estimate total posts and cost
    with get_conn() as conn:
        total_posted = conn.execute(
            "SELECT COUNT(*) as n FROM posts WHERE campaign_name=? AND status='posted'",
            (campaign_name,)
        ).fetchone()["n"]

        total_engagement = conn.execute(
            "SELECT SUM(upvotes + 3*comments) as s FROM posts WHERE campaign_name=? AND status='posted'",
            (campaign_name,)
        ).fetchone()["s"] or 0

    est_total_cost = total_posted * AVG_TOKENS_PER_POST / 1_000_000 * (
        DEEPSEEK_INPUT_COST_PER_1M * 0.67 + DEEPSEEK_OUTPUT_COST_PER_1M * 0.33
    )

    best = scores[0] if scores else None

    return {
        "campaign": campaign_name,
        "total_posts": total_posted,
        "total_engagement_score": int(total_engagement),
        "estimated_total_cost_usd": round(est_total_cost, 5),
        "cost_per_score_point": round(est_total_cost / max(total_engagement, 1), 6),
        "best_strategy": f"{best['platform']}/{best['post_type']}" if best else "insufficient_data",
        "best_avg_score": round(best["total_score"] / best["n_posts"], 1) if best else 0,
        "token_rate": f"DeepSeek ${DEEPSEEK_INPUT_COST_PER_1M}/1M input, ${DEEPSEEK_OUTPUT_COST_PER_1M}/1M output",
    }
