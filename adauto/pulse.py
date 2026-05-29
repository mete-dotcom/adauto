"""
adauto pulse scanner — read the community before writing for it.

"Nabzı ölç, nabza göre şerbet ver."

Fetches recent posts from Reddit (public JSON API, zero auth required),
extracts actionable signal, and builds a compact context string (<350 tokens)
that gets injected into the generation prompt so adauto writes posts that
feel native to each community rather than obviously promotional.

Reddit JSON API endpoints used (public, no auth):
  /r/{sub}/hot.json?limit=50
  /r/{sub}/top.json?t=week&limit=25

Cache: ~/.adauto/pulse_cache/{subreddit}_{YYYYMMDD}.json  (TTL: 6 hours)
"""
from __future__ import annotations

import json
import re
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import xml.etree.ElementTree as ET

import requests

# ── config ────────────────────────────────────────────────────────────────────

PULSE_CACHE_DIR = Path.home() / ".adauto" / "pulse_cache"
PULSE_CACHE_DIR.mkdir(parents=True, exist_ok=True)

CACHE_TTL_SECONDS = 6 * 3600   # re-scan at most every 6 hours

REQUEST_TIMEOUT   = 12          # seconds
MAX_POSTS_HOT     = 50
MAX_POSTS_TOP     = 25

_REDDIT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; adauto/0.1; +https://github.com/mete-dotcom/adauto)",
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}

# Atom namespace used in Reddit RSS feeds
_ATOM_NS = "http://www.w3.org/2005/Atom"

# ── English stopwords (lightweight, no NLTK needed) ──────────────────────────

_STOPWORDS = frozenset("""
a about above after again against all also am an and another any are aren't as at
be because been before being below between both but by can can't cannot could
did didn't do does doesn't doing don't down during each few for from further
get got had hadn't has hasn't have haven't having he he'd he'll he's her here
here's hers herself him himself his how how's i i'd i'll i'm i've if in into
is isn't it it's its itself just let's like me more most mustn't my myself
no nor not of off on once only or other ought our ours ourselves out own
same shan't she she'd she'll she's should shouldn't so some such than that
that's the their theirs them themselves then there there's these they they'd
they'll they're they've this those through to too under until up very was
wasn't we we'd we'll we're we've were weren't what what's when when's where
where's which while who who's whom why why's will with won't would wouldn't
you you'd you'll you're you've your yours yourself yourselves
""".split())

# Patterns that signal a question, tutorial, or announcement
_TITLE_PATTERNS = {
    "question":    re.compile(r"\?$|^(how|what|why|when|which|who|where|should|can|do|does|is|are)\b", re.I),
    "show_hn":     re.compile(r"^show\s+hn|^show\s+r/", re.I),
    "tutorial":    re.compile(r"\b(tutorial|guide|how.to|step.by.step|walkthrough|learn)\b", re.I),
    "comparison":  re.compile(r"\bvs\.?\b|\bversus\b|\bcompare\b|\balternative\b", re.I),
    "update":      re.compile(r"\b(v\d+|version|release|update|changelog|new feature)\b", re.I),
    "rant":        re.compile(r"\b(rant|frustrated|annoyed|tired of|hate|ugh)\b", re.I),
}


# ── data fetcher ─────────────────────────────────────────────────────────────

def _parse_rss_posts(xml_text: str) -> list[dict]:
    """Parse Reddit Atom/RSS feed into a list of post-like dicts."""
    posts = []
    try:
        root = ET.fromstring(xml_text)
        ns = {"a": _ATOM_NS}
        for entry in root.findall("a:entry", ns):
            title_el  = entry.find("a:title", ns)
            content_el = entry.find("a:content", ns)
            link_el   = entry.find("a:link", ns)
            title   = title_el.text if title_el is not None else ""
            content = content_el.text if content_el is not None else ""
            link    = link_el.get("href", "") if link_el is not None else ""

            # Strip HTML tags from content for text analysis
            clean_content = re.sub(r"<[^>]+>", " ", content or "")
            clean_content = re.sub(r"\s+", " ", clean_content).strip()

            posts.append({
                "title":    title or "",
                "selftext": clean_content[:500],
                "url":      link,
                "score":    0,           # RSS doesn't include scores
                "num_comments": 0,
                "is_self":  not link.startswith("https://i.") and ".redd.it" not in link,
            })
    except ET.ParseError:
        pass
    return posts


def _fetch_subreddit_rss(subreddit: str, sort: str = "hot") -> list[dict]:
    """
    Fetch posts from Reddit's public RSS/Atom feed.
    Falls back to PRAW if configured (richer data with scores).
    """
    # Try PRAW first if credentials are available
    praw_posts = _try_praw(subreddit, sort)
    if praw_posts:
        return praw_posts

    # Use RSS feed (always public, no auth)
    url = f"https://www.reddit.com/r/{subreddit}/{sort}.rss?limit={MAX_POSTS_HOT}"
    try:
        r = requests.get(url, headers=_REDDIT_HEADERS, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        return _parse_rss_posts(r.text)
    except Exception:
        return []


def _try_praw(subreddit: str, sort: str = "hot") -> list[dict]:
    """
    Attempt to use PRAW for richer data (scores, comments, flairs).
    Requires REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET in env or ~/.adauto/config.
    Returns empty list if PRAW not available or not configured.
    """
    import os
    client_id     = os.environ.get("REDDIT_CLIENT_ID", "")
    client_secret = os.environ.get("REDDIT_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        return []
    try:
        import praw
        reddit = praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent="adauto/0.1 (developer marketing tool)",
        )
        sub    = reddit.subreddit(subreddit)
        method = getattr(sub, sort, sub.hot)
        subs   = list(method(limit=MAX_POSTS_HOT))
        return [{
            "title":        s.title,
            "selftext":     (s.selftext or "")[:500],
            "score":        s.score,
            "num_comments": s.num_comments,
            "is_self":      s.is_self,
            "link_flair_text": getattr(s, "link_flair_text", None),
        } for s in subs]
    except Exception:
        return []


def _load_cache(subreddit: str) -> Optional[dict]:
    """Return cached pulse data if fresh, else None."""
    ts  = datetime.now(timezone.utc).strftime("%Y%m%d_%H")
    path = PULSE_CACHE_DIR / f"{subreddit}_{ts}.json"
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if time.time() - data.get("_fetched_at", 0) < CACHE_TTL_SECONDS:
                return data
        except Exception:
            pass
    return None


def _save_cache(subreddit: str, data: dict) -> None:
    ts   = datetime.now(timezone.utc).strftime("%Y%m%d_%H")
    path = PULSE_CACHE_DIR / f"{subreddit}_{ts}.json"
    try:
        data["_fetched_at"] = time.time()
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


# ── core analysis ─────────────────────────────────────────────────────────────

def _extract_keywords(texts: list[str], top_n: int = 15) -> list[str]:
    """Extract top N non-stopword unigrams + bigrams from a list of texts."""
    words = []
    for text in texts:
        tokens = re.findall(r"[a-z][a-z0-9_]*", text.lower())
        tokens = [t for t in tokens if t not in _STOPWORDS and len(t) > 2]
        words.extend(tokens)
        # bigrams
        for a, b in zip(tokens, tokens[1:]):
            words.append(f"{a} {b}")
    freq = Counter(words)
    return [kw for kw, _ in freq.most_common(top_n)]


def _detect_pattern(title: str) -> str:
    for pname, pat in _TITLE_PATTERNS.items():
        if pat.search(title):
            return pname
    return "statement"


def _analyse_posts(posts: list[dict]) -> dict:
    """Extract actionable insights from a list of Reddit post dicts."""
    if not posts:
        return {}

    scores          = [p.get("score", 0) for p in posts]
    num_comments    = [p.get("num_comments", 0) for p in posts]
    title_lengths   = [len(p.get("title", "")) for p in posts]
    body_lengths    = [len(p.get("selftext", "")) for p in posts if p.get("is_self")]

    # Score tiers
    top_20pct = sorted(scores, reverse=True)[:max(1, len(scores)//5)]
    median_score = sorted(scores)[len(scores)//2] if scores else 0

    # Top-performing post titles (top 20% by score)
    top_threshold = top_20pct[-1] if top_20pct else 0
    top_posts = [p for p in posts if p.get("score", 0) >= top_threshold]

    top_titles      = [p.get("title", "") for p in top_posts[:8]]
    top_keywords    = _extract_keywords(
        [p.get("title", "") + " " + p.get("selftext", "")[:200] for p in top_posts],
        top_n=12,
    )

    # Pattern distribution in top posts
    pattern_counts: Counter = Counter()
    for p in top_posts:
        pattern_counts[_detect_pattern(p.get("title", ""))] += 1
    best_pattern = pattern_counts.most_common(1)[0][0] if pattern_counts else "statement"

    # Flair distribution
    flairs = Counter(
        p.get("link_flair_text") or p.get("link_flair_css_class") or "none"
        for p in posts
        if p.get("link_flair_text") or p.get("link_flair_css_class")
    )

    # Preferred body length (text posts)
    avg_body_len = int(sum(body_lengths) / len(body_lengths)) if body_lengths else 0

    # What's trending: top keywords from titles in last 24h (approximate via new)
    return {
        "median_score":   median_score,
        "top_20pct_threshold": top_threshold,
        "avg_title_len":  int(sum(title_lengths) / len(title_lengths)) if title_lengths else 60,
        "avg_body_len":   avg_body_len,
        "avg_comments":   int(sum(num_comments) / len(num_comments)) if num_comments else 0,
        "top_keywords":   top_keywords,
        "top_titles":     top_titles[:5],
        "best_pattern":   best_pattern,
        "pattern_dist":   dict(pattern_counts.most_common(4)),
        "top_flairs":     [f for f, _ in flairs.most_common(4)],
        "total_posts_scanned": len(posts),
    }


# ── public API ────────────────────────────────────────────────────────────────

def scan_subreddit(subreddit: str) -> dict:
    """
    Scan a subreddit and return pulse data.
    Uses cache if fresh (TTL: 6h).
    Data source: RSS feed (always free) or PRAW (richer, requires credentials).
    """
    cached = _load_cache(subreddit)
    if cached:
        return cached

    hot_posts = _fetch_subreddit_rss(subreddit, sort="hot")
    top_posts = _fetch_subreddit_rss(subreddit, sort="top")

    all_posts = hot_posts + top_posts
    data = _analyse_posts(all_posts)
    data["subreddit"]   = subreddit
    data["scanned_at"]  = datetime.now(timezone.utc).isoformat()
    data["data_source"] = "praw" if (hot_posts and hot_posts[0].get("score", 0) > 0) else "rss"

    # Only cache if we actually got posts — don't cache empty results
    if all_posts:
        _save_cache(subreddit, data)
    return data


def build_pulse_context(subreddit: str, post_type: str, product: str) -> str:
    """
    Build a compact community-pulse context string for injection into the
    generation prompt. Stays under 350 tokens.

    Returns empty string if scanning fails — never blocks generation.
    """
    try:
        data = scan_subreddit(subreddit)
    except Exception:
        return ""

    if not data:
        return ""

    top_kw  = ", ".join(data.get("top_keywords", [])[:8])
    titles  = data.get("top_titles", [])
    best_p  = data.get("best_pattern", "statement")
    avg_t   = data.get("avg_title_len", 60)
    avg_b   = data.get("avg_body_len", 400)
    thresh  = data.get("top_20pct_threshold", 100)
    flairs  = ", ".join(data.get("top_flairs", [])[:3]) or "none"

    title_examples = "\n".join(f'    • "{t[:80]}"' for t in titles[:3])

    ctx = f"""COMMUNITY PULSE — r/{subreddit} (live scan, {data.get('total_posts_scanned',0)} posts)
Current trending keywords: {top_kw}
What top-performing titles look like ({best_p} pattern dominates):
{title_examples}
Stats: avg title {avg_t} chars | avg body {avg_b} chars | top-20% threshold >={thresh} upvotes
Preferred flairs: {flairs}

CALIBRATION RULES for r/{subreddit}:
- Match vocabulary and tone from the trending keywords above
- Title structure: lean toward "{best_p}" (what's scoring best right now)
- Body length: aim for ~{avg_b} chars for text posts
- Sound like a community member, not a marketer
- Do NOT mention {product} in the title if post_type is "question" — let the body do the work"""

    return ctx


def scan_all_subreddits(subreddits: list[str]) -> dict[str, dict]:
    """Scan multiple subreddits and return combined pulse data keyed by name."""
    results = {}
    for sub in subreddits:
        try:
            results[sub] = scan_subreddit(sub)
        except Exception:
            results[sub] = {}
    return results


def pulse_summary(subreddits: list[str]) -> str:
    """One-line summary of pulse across multiple subreddits — for display."""
    lines = []
    for sub in subreddits:
        try:
            d = scan_subreddit(sub)
            if d:
                kw = ", ".join(d.get("top_keywords", [])[:4])
                lines.append(f"  r/{sub:25s} top keywords: {kw}")
        except Exception:
            lines.append(f"  r/{sub:25s} [scan failed]")
    return "\n".join(lines) if lines else "  (no subreddits configured)"
