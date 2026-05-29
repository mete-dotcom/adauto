"""
adauto signal hunter — zero-cost cross-platform signal detection.

Design principle (the immortality rule):
  Zero LLM tokens. Zero API keys (unless the user already has Reddit/GitHub
  creds for richer data — but the fallback always works without them).
  All detection is regex + keyword matching on free public endpoints.

Supported platforms (all free, no auth required for basic mode):
  reddit    — public RSS (.rss, no auth) + PRAW if configured
  hn        — Algolia HN Search API (free, no key)
  github    — public GitHub Search API (60 req/h unauthed, 5000 authed)
  pypi      — PyPI RSS new-packages feed + package JSON
  devto     — dev.to public API (no key for search)
  so        — Stack Overflow public API (free tier, 300 req/day)

Chain rule:
  When a signal is detected on platform A, the hunter automatically fires
  a cross-platform query using the same extracted keywords + title fragments.
  Signals on different platforms referencing the same need are linked in
  the signal store (chain_ids).
"""
from __future__ import annotations

import re
import time
import json
import urllib.request
import urllib.parse
import urllib.error
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Callable

from . import signal_store as store

# ── signal result ─────────────────────────────────────────────────────────────

@dataclass
class Signal:
    platform: str
    url: str
    title: str
    body: str = ""
    author: str = ""
    score: int = 0
    matched_kw: list[str] = field(default_factory=list)


# ── http helpers ──────────────────────────────────────────────────────────────

_UA = "adauto-signal-hunter/0.1 (https://adauto.dev)"

def _get(url: str, timeout: int = 10) -> str | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _UA,
                                                    "Accept": "application/json,*/*"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", errors="replace")
    except Exception:
        return None


def _json_get(url: str) -> dict | list | None:
    raw = _get(url)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


# ── keyword matcher ───────────────────────────────────────────────────────────

def _match_kw(text: str, keywords: list[str]) -> list[str]:
    """Return which keywords appear in text (case-insensitive, word-boundary)."""
    t = text.lower()
    return [kw for kw in keywords if re.search(r'\b' + re.escape(kw.lower()) + r'\b', t)]


# ── platform adapters ─────────────────────────────────────────────────────────

def hunt_reddit(keywords: list[str], subreddits: list[str],
                limit: int = 25) -> list[Signal]:
    """Scan subreddit RSS feeds for keyword matches. Zero auth."""
    signals = []
    for sub in subreddits:
        raw = _get(f"https://www.reddit.com/r/{sub}/new.rss?limit={limit}")
        if not raw:
            raw = _get(f"https://www.reddit.com/r/{sub}/hot.rss?limit={limit}")
        if not raw:
            continue
        try:
            root = ET.fromstring(raw)
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            for entry in root.findall("atom:entry", ns):
                title_el = entry.find("atom:title", ns)
                content_el = entry.find("atom:content", ns)
                link_el = entry.find("atom:link", ns)
                author_el = entry.find("atom:author/atom:name", ns)
                title = (title_el.text or "") if title_el is not None else ""
                body = (content_el.text or "") if content_el is not None else ""
                url = link_el.get("href", "") if link_el is not None else ""
                author = (author_el.text or "") if author_el is not None else ""
                combined = f"{title} {body}"
                matched = _match_kw(combined, keywords)
                if matched:
                    signals.append(Signal("reddit", url, title,
                                          body[:400], author, 0, matched))
        except Exception:
            continue
    return signals


def hunt_hn(keywords: list[str], limit: int = 20) -> list[Signal]:
    """Hacker News via Algolia search API (free, no key)."""
    signals = []
    # Use plain keywords joined with spaces — Algolia treats them as OR.
    # Quoted multi-word phrases are too strict and return 0 results.
    query = urllib.parse.quote(" ".join(keywords[:4]))
    # tags= accepts a single tag value; "story,comment" returns 0 (AND filter).
    # Fetch stories only — most signal value, title always present.
    data = _json_get(
        f"https://hn.algolia.com/api/v1/search_by_date"
        f"?query={query}&tags=story&hitsPerPage={limit}"
    )
    if not isinstance(data, dict):
        return []
    for hit in data.get("hits", []):
        title = hit.get("title") or hit.get("comment_text", "")[:80] or ""
        body = hit.get("comment_text") or hit.get("story_text") or ""
        url = hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID','')}"
        author = hit.get("author", "")
        score = hit.get("points") or hit.get("num_comments", 0) or 0
        # HN story bodies are often null — match on title alone is valid
        combined = f"{title} {body}"
        matched = _match_kw(combined, keywords) or _match_kw(title, keywords)
        if matched:
            signals.append(Signal("hn", url, title, body[:400], author, score, matched))
    return signals


def hunt_github(keywords: list[str], limit: int = 20,
                token: str | None = None) -> list[Signal]:
    """GitHub Issues/Discussions search (60 req/h unauthed, 5000 authed)."""
    signals = []
    q = urllib.parse.quote(" ".join(keywords[:3]) + " is:issue is:open")
    headers: dict = {"User-Agent": _UA, "Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    url = f"https://api.github.com/search/issues?q={q}&sort=updated&per_page={limit}"
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
    except Exception:
        return []
    for item in data.get("items", []):
        title = item.get("title", "")
        body = (item.get("body") or "")[:400]
        url = item.get("html_url", "")
        author = item.get("user", {}).get("login", "")
        score = item.get("reactions", {}).get("+1", 0) + item.get("comments", 0)
        matched = _match_kw(f"{title} {body}", keywords)
        if matched:
            signals.append(Signal("github", url, title, body, author, score, matched))
    return signals


def hunt_pypi(keywords: list[str], limit: int = 15) -> list[Signal]:
    """PyPI new packages RSS — discovers tools in the same space."""
    raw = _get("https://pypi.org/rss/updates.xml")
    if not raw:
        return []
    signals = []
    try:
        root = ET.fromstring(raw)
        for item in root.findall(".//item")[:limit * 3]:
            title = (item.findtext("title") or "")
            desc = (item.findtext("description") or "")
            link = (item.findtext("link") or "")
            combined = f"{title} {desc}"
            matched = _match_kw(combined, keywords)
            if matched:
                signals.append(Signal("pypi", link, title, desc[:400], "", 0, matched))
    except Exception:
        pass
    return signals[:limit]


def hunt_devto(keywords: list[str], limit: int = 15) -> list[Signal]:
    """dev.to public article search API (no key required)."""
    signals = []
    for kw in keywords[:3]:
        q = urllib.parse.quote(kw)
        data = _json_get(f"https://dev.to/api/articles?tag={q}&per_page={limit}&state=fresh")
        if not isinstance(data, list):
            data = _json_get(f"https://dev.to/api/articles?q={q}&per_page={limit}")
        if not isinstance(data, list):
            continue
        for a in data:
            title = a.get("title", "")
            desc = a.get("description") or a.get("body_markdown", "")[:400]
            url = a.get("url", "")
            author = a.get("user", {}).get("username", "")
            score = a.get("public_reactions_count", 0) + a.get("comments_count", 0)
            matched = _match_kw(f"{title} {desc}", keywords)
            if matched:
                signals.append(Signal("devto", url, title, desc[:400],
                                      author, score, matched))
    return signals[:limit]


def hunt_so(keywords: list[str], limit: int = 15) -> list[Signal]:
    """Stack Overflow free API (300 req/day unauthed, 10000 authed)."""
    q = urllib.parse.quote(";".join(keywords[:3]))
    data = _json_get(
        f"https://api.stackexchange.com/2.3/search/advanced"
        f"?q={q}&order=desc&sort=activity&site=stackoverflow"
        f"&pagesize={limit}&filter=withbody"
    )
    if not isinstance(data, dict):
        return []
    signals = []
    for item in data.get("items", []):
        title = item.get("title", "")
        body = re.sub(r"<[^>]+>", " ", item.get("body", ""))[:400]
        url = item.get("link", "")
        author = item.get("owner", {}).get("display_name", "")
        score = item.get("score", 0) + item.get("answer_count", 0)
        matched = _match_kw(f"{title} {body}", keywords)
        if matched:
            signals.append(Signal("so", url, title, body, author, score, matched))
    return signals


# ── platform registry ─────────────────────────────────────────────────────────

# platform_name → (hunter_fn, supports_subreddit_arg)
_HUNTERS: dict[str, Callable] = {
    "hn":     hunt_hn,
    "github": hunt_github,
    "pypi":   hunt_pypi,
    "devto":  hunt_devto,
    "so":     hunt_so,
}


# ── cross-platform chain ──────────────────────────────────────────────────────

def _extract_chain_terms(signal: Signal, max_terms: int = 4) -> list[str]:
    """Pull the most specific terms from a signal for cross-platform search."""
    # Use matched keywords + 2-word title fragments
    terms = list(signal.matched_kw[:2])
    words = re.findall(r"[A-Za-z][a-z]{3,}", signal.title)
    seen = {t.lower() for t in terms}
    for w in words:
        if w.lower() not in seen and len(terms) < max_terms:
            terms.append(w)
            seen.add(w.lower())
    return terms


def chase(source_signal: Signal, keywords: list[str],
          platforms: list[str] | None = None,
          github_token: str | None = None) -> list[Signal]:
    """
    Cross-platform chain: given a signal found on one platform,
    search the others for the same need/discussion.
    Returns all corroborating signals found.
    """
    chain_terms = _extract_chain_terms(source_signal, max_terms=4)
    if not chain_terms:
        chain_terms = keywords[:2]
    targets = platforms or list(_HUNTERS)
    # Don't re-search the originating platform
    targets = [p for p in targets if p != source_signal.platform]
    corroborating = []
    for p in targets:
        fn = _HUNTERS.get(p)
        if fn is None:
            continue
        try:
            if p == "github":
                found = fn(chain_terms, token=github_token)
            else:
                found = fn(chain_terms)
            corroborating.extend(found)
            time.sleep(0.3)  # polite pacing, no hammering
        except Exception:
            continue
    return corroborating


# ── main hunt cycle ───────────────────────────────────────────────────────────

def run_hunt(campaign_name: str,
             keywords: list[str],
             subreddits: list[str] | None = None,
             platforms: list[str] | None = None,
             chain: bool = True,
             github_token: str | None = None,
             verbose: bool = False) -> dict:
    """
    Full hunt cycle for a campaign.

    1. Scan configured platforms for keyword matches.
    2. For every new signal: fire cross-platform chain search.
    3. Store everything in signal_store (dedup by URL).
    4. Return summary: {new_signals, chained, platforms_scanned}.
    """
    store.init()
    all_platforms = platforms or ["reddit", "hn", "github", "devto", "so"]
    subs = subreddits or ["programming", "Python", "SideProject"]
    new_count = 0
    chained_count = 0
    primary_signals: list[Signal] = []

    # ── Phase 1: primary scan ──────────────────────────────────────────────────
    for p in all_platforms:
        if verbose:
            print(f"  [hunt] {p} ...", end="", flush=True)
        found: list[Signal] = []
        try:
            if p == "reddit":
                found = hunt_reddit(keywords, subs)
            elif p == "github":
                found = hunt_github(keywords, token=github_token)
            else:
                fn = _HUNTERS.get(p)
                if fn:
                    found = fn(keywords)
        except Exception as e:
            if verbose:
                print(f" error ({e})")
            continue

        if verbose:
            print(f" {len(found)} match(es)")
        primary_signals.extend(found)
        for sig in found:
            sid = store.upsert(sig.platform, sig.url, sig.title, sig.body,
                               sig.author, sig.score, sig.matched_kw, campaign_name)
            if sid is not None:
                new_count += 1

        time.sleep(0.5)  # polite inter-platform pacing

    # ── Phase 2: chain (cross-platform trace) ─────────────────────────────────
    if chain and primary_signals:
        # Only chain the top-scored/most-matched primaries (max 5, avoid hammering)
        primaries_to_chase = sorted(primary_signals,
                                    key=lambda s: (len(s.matched_kw), s.score),
                                    reverse=True)[:5]
        for src in primaries_to_chase:
            corroborate = chase(src, keywords, platforms=all_platforms,
                                github_token=github_token)
            chain_ids: list[int] = []
            for cs in corroborate:
                cid = store.upsert(cs.platform, cs.url, cs.title, cs.body,
                                   cs.author, cs.score, cs.matched_kw, campaign_name)
                if cid is not None:
                    chained_count += 1
                    chain_ids.append(cid)
            if chain_ids:
                # Find the source signal's store id and link the chain
                all_new = store.get_all(campaign_name, limit=500)
                src_row = next((r for r in all_new if r["signal_url"] == src.url), None)
                if src_row:
                    store.link_chain(src_row["id"], chain_ids)

    return {
        "new_signals":      new_count,
        "chained":          chained_count,
        "platforms_scanned": all_platforms,
        "total_new":        new_count + chained_count,
    }
