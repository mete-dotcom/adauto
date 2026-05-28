"""
Analytics & adaptive learning — track engagement, score post styles, feed learnings back.

Paradigm: deterministic signal loop.
  1. After posting, URLs are stored in DB.
  2. check_engagement() polls platform APIs for upvotes/comments.
  3. score_styles() computes a performance score per (platform, post_type, subreddit).
  4. best_examples() returns the top-performing posts as few-shot examples for generator.

No ML, no cloud. Pure SQLite + platform APIs.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Optional

from .db import get_conn


# ── Engagement polling ────────────────────────────────────────────────────────


def check_reddit_engagement(post_id: int, url: str) -> dict:
    """
    Poll Reddit API for upvotes/comments on a posted URL.
    URL format: https://reddit.com/r/.../comments/XXXXX/...
    Returns {"upvotes": N, "comments": N} or empty dict on failure.
    """
    try:
        import requests
        # Reddit JSON API: append .json to the post URL
        json_url = url.rstrip("/") + ".json"
        resp = requests.get(
            json_url,
            headers={"User-Agent": "adauto/0.1"},
            timeout=10,
        )
        if resp.status_code != 200:
            return {}
        data = resp.json()
        listing = data[0]["data"]["children"][0]["data"]
        return {
            "upvotes": listing.get("ups", 0),
            "comments": listing.get("num_comments", 0),
        }
    except Exception:
        return {}


def check_engagement_all(max_posts: int = 50) -> int:
    """
    Poll engagement for all recently posted URLs.
    Returns number of posts updated.
    """
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT id, platform, url FROM posts
               WHERE status='posted' AND url IS NOT NULL
               ORDER BY posted_at DESC LIMIT ?""",
            (max_posts,),
        ).fetchall()

    updated = 0
    for row in rows:
        post_id, platform, url = row["id"], row["platform"], row["url"]
        metrics = {}
        if platform == "reddit":
            metrics = check_reddit_engagement(post_id, url)
        # future: devto, twitter

        if metrics:
            _record_metrics(post_id, metrics)
            _update_post_metrics(post_id, metrics)
            updated += 1
        time.sleep(0.5)  # be polite

    return updated


def _record_metrics(post_id: int, metrics: dict) -> None:
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO metrics (post_id, upvotes, comments, clicks)
               VALUES (?, ?, ?, ?)""",
            (post_id,
             metrics.get("upvotes", 0),
             metrics.get("comments", 0),
             metrics.get("clicks", 0)),
        )


def _update_post_metrics(post_id: int, metrics: dict) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE posts SET upvotes=?, comments=? WHERE id=?",
            (metrics.get("upvotes", 0), metrics.get("comments", 0), post_id),
        )


# ── Scoring ───────────────────────────────────────────────────────────────────


def score_styles(campaign_name: str = None) -> list[dict]:
    """
    Compute performance scores per (platform, post_type).
    Score = weighted sum of upvotes + 3×comments (comments signal deeper engagement).

    Returns list sorted by score descending.
    """
    with get_conn() as conn:
        q = """
            SELECT platform, post_type,
                   COUNT(*) as n,
                   AVG(upvotes) as avg_up,
                   AVG(comments) as avg_cm,
                   SUM(upvotes + 3*comments) as total_score
            FROM posts
            WHERE status='posted'
        """
        args = []
        if campaign_name:
            q += " AND campaign_name=?"
            args.append(campaign_name)
        q += " GROUP BY platform, post_type ORDER BY total_score DESC"
        rows = conn.execute(q, args).fetchall()

    return [
        {
            "platform": r["platform"],
            "post_type": r["post_type"],
            "n_posts": r["n"],
            "avg_upvotes": round(r["avg_up"] or 0, 1),
            "avg_comments": round(r["avg_cm"] or 0, 1),
            "total_score": r["total_score"] or 0,
        }
        for r in rows
    ]


def best_post_type(campaign_name: str, platform: str,
                   fallback: str = "showcase") -> str:
    """Return the best-performing post_type for a campaign+platform combo."""
    scores = score_styles(campaign_name)
    plat_scores = [s for s in scores if s["platform"] == platform and s["n_posts"] >= 2]
    if plat_scores:
        return plat_scores[0]["post_type"]
    return fallback


# ── Few-shot examples for adaptive generation ─────────────────────────────────


def best_examples(campaign_name: str, platform: str,
                  post_type: str = None, limit: int = 3) -> list[dict]:
    """
    Return top-performing posts as few-shot examples for the generator.
    Sorted by (upvotes + 3*comments) descending.
    """
    with get_conn() as conn:
        q = """
            SELECT title, body, upvotes, comments, post_type
            FROM posts
            WHERE status='posted'
              AND campaign_name=?
              AND platform=?
              AND (upvotes + comments) > 0
        """
        args = [campaign_name, platform]
        if post_type:
            q += " AND post_type=?"
            args.append(post_type)
        q += " ORDER BY (upvotes + 3*comments) DESC LIMIT ?"
        args.append(limit)
        rows = conn.execute(q, args).fetchall()

    return [
        {
            "post_type": r["post_type"],
            "title": r["title"],
            "body": r["body"][:500] if r["body"] else "",
            "upvotes": r["upvotes"],
            "comments": r["comments"],
        }
        for r in rows
    ]


def build_learning_context(campaign_name: str, platform: str,
                           post_type: str = None) -> str:
    """
    Build a 'what works' context block for the generator prompt.
    Returns empty string if no data yet.
    """
    examples = best_examples(campaign_name, platform, post_type)
    if not examples:
        return ""

    lines = ["WHAT HAS WORKED WELL (real posts, ranked by engagement):"]
    for i, ex in enumerate(examples, 1):
        lines.append(
            f"\nExample {i} [{ex['post_type']}] "
            f"({ex['upvotes']} upvotes, {ex['comments']} comments):"
        )
        if ex["title"]:
            lines.append(f"  Title: {ex['title']}")
        lines.append(f"  Body (excerpt): {ex['body'][:300]}")

    lines.append(
        "\nLearn from these: use similar tone, depth, and hook style "
        "but write completely new content."
    )
    return "\n".join(lines)
