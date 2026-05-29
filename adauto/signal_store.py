"""
adauto signal store — SQLite backing for cross-platform signals.

Zero API cost: all signals arrive from free public endpoints (RSS, JSON, HTML).
Keeps seen/acted state so the hunter never double-reports the same thread.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

_DB = Path.home() / ".adauto" / "signals.db"


def _conn() -> sqlite3.Connection:
    _DB.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(_DB))
    c.row_factory = sqlite3.Row
    return c


def init() -> None:
    with _conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS signals (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            platform    TEXT NOT NULL,          -- reddit | hn | github | pypi | devto | so
            signal_url  TEXT UNIQUE NOT NULL,   -- canonical URL (dedup key)
            title       TEXT,
            body_snip   TEXT,                   -- first 400 chars of body/description
            author      TEXT,
            score       INTEGER DEFAULT 0,
            matched_kw  TEXT,                   -- JSON list of keywords that matched
            campaign    TEXT,                   -- which campaign this signal belongs to
            chain_ids   TEXT,                   -- JSON list of related signal IDs (chain)
            status      TEXT DEFAULT 'new',     -- new | reviewed | acted | ignored
            found_at    TEXT DEFAULT (datetime('now')),
            acted_at    TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_platform ON signals(platform);
        CREATE INDEX IF NOT EXISTS idx_campaign ON signals(campaign);
        CREATE INDEX IF NOT EXISTS idx_status   ON signals(status);
        """)


def upsert(platform: str, url: str, title: str, body_snip: str,
           author: str, score: int, matched_kw: list[str], campaign: str) -> int | None:
    """Insert a new signal. Returns new row id, or None if already seen."""
    init()
    with _conn() as c:
        try:
            cur = c.execute(
                """INSERT INTO signals
                   (platform, signal_url, title, body_snip, author, score,
                    matched_kw, campaign)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (platform, url, title[:300], body_snip[:400], author, score,
                 json.dumps(matched_kw), campaign),
            )
            return cur.lastrowid
        except sqlite3.IntegrityError:
            return None  # already in DB


def link_chain(signal_id: int, related_ids: list[int]) -> None:
    """Record cross-platform chain links for a signal."""
    init()
    with _conn() as c:
        row = c.execute("SELECT chain_ids FROM signals WHERE id=?", (signal_id,)).fetchone()
        if row:
            existing = json.loads(row["chain_ids"] or "[]")
            merged = list(set(existing + related_ids))
            c.execute("UPDATE signals SET chain_ids=? WHERE id=?",
                      (json.dumps(merged), signal_id))


def get_new(campaign: str | None = None, limit: int = 50) -> list[dict]:
    init()
    with _conn() as c:
        q = "SELECT * FROM signals WHERE status='new'"
        args: list = []
        if campaign:
            q += " AND campaign=?"
            args.append(campaign)
        q += " ORDER BY score DESC, found_at DESC LIMIT ?"
        args.append(limit)
        return [dict(r) for r in c.execute(q, args).fetchall()]


def get_all(campaign: str | None = None, limit: int = 200) -> list[dict]:
    init()
    with _conn() as c:
        q = "SELECT * FROM signals"
        args: list = []
        if campaign:
            q += " WHERE campaign=?"
            args.append(campaign)
        q += " ORDER BY score DESC, found_at DESC LIMIT ?"
        args.append(limit)
        return [dict(r) for r in c.execute(q, args).fetchall()]


def mark(signal_id: int, status: str) -> None:
    init()
    with _conn() as c:
        extra = ", acted_at=datetime('now')" if status == "acted" else ""
        c.execute(f"UPDATE signals SET status=?{extra} WHERE id=?", (status, signal_id))


def stats() -> dict:
    init()
    with _conn() as c:
        rows = c.execute(
            "SELECT platform, status, COUNT(*) n FROM signals GROUP BY platform, status"
        ).fetchall()
        out: dict = {}
        for r in rows:
            out.setdefault(r["platform"], {})[r["status"]] = r["n"]
        return out
