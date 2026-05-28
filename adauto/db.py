"""SQLite state store for adauto — posts, campaigns, engagement."""
import sqlite3
import json
from pathlib import Path
from datetime import datetime, timezone

DB_PATH = Path.home() / ".adauto" / "adauto.db"


def get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS campaigns (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            name      TEXT UNIQUE NOT NULL,
            product   TEXT NOT NULL,
            config    TEXT NOT NULL,  -- JSON
            enabled   INTEGER DEFAULT 1,
            created   TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS posts (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_name TEXT NOT NULL,
            platform      TEXT NOT NULL,
            post_type     TEXT NOT NULL,  -- showcase | tutorial | question | comment
            title         TEXT,
            body          TEXT,
            url           TEXT,           -- posted URL / thread URL
            status        TEXT DEFAULT 'pending_approval',  -- pending_approval | approved | queued | posted | failed | skipped
            scheduled_at  TEXT,
            posted_at     TEXT,
            error         TEXT,
            upvotes       INTEGER DEFAULT 0,
            comments      INTEGER DEFAULT 0,
            created       TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS metrics (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id     INTEGER REFERENCES posts(id),
            checked_at  TEXT DEFAULT (datetime('now')),
            upvotes     INTEGER DEFAULT 0,
            comments    INTEGER DEFAULT 0,
            clicks      INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS kv (
            key   TEXT PRIMARY KEY,
            value TEXT,
            updated TEXT DEFAULT (datetime('now'))
        );
        """)


def kv_set(key: str, value) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO kv (key, value, updated) VALUES (?, ?, datetime('now'))",
            (key, json.dumps(value))
        )


def kv_get(key: str, default=None):
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM kv WHERE key = ?", (key,)).fetchone()
        return json.loads(row["value"]) if row else default


def add_post(campaign_name: str, platform: str, post_type: str,
             title: str, body: str, scheduled_at: str = None) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO posts (campaign_name, platform, post_type, title, body, scheduled_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (campaign_name, platform, post_type, title, body, scheduled_at)
        )
        return cur.lastrowid


def mark_posted(post_id: int, url: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE posts SET status='posted', url=?, posted_at=datetime('now') WHERE id=?",
            (url, post_id)
        )


def mark_failed(post_id: int, error: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE posts SET status='failed', error=? WHERE id=?",
            (error, post_id)
        )


def approve_post(post_id: int) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE posts SET status='approved' WHERE id=?", (post_id,))


def skip_post(post_id: int) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE posts SET status='skipped' WHERE id=?", (post_id,))


def update_post_body(post_id: int, title: str, body: str) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE posts SET title=?, body=? WHERE id=?",
                     (title, body, post_id))


def get_pending_approval(campaign_name: str = None, platform: str = None) -> list:
    with get_conn() as conn:
        q = "SELECT * FROM posts WHERE status='pending_approval'"
        args = []
        if campaign_name:
            q += " AND campaign_name=?"
            args.append(campaign_name)
        if platform:
            q += " AND platform=?"
            args.append(platform)
        q += " ORDER BY created ASC"
        return [dict(r) for r in conn.execute(q, args).fetchall()]


def get_approved(platform: str = None) -> list:
    with get_conn() as conn:
        q = "SELECT * FROM posts WHERE status='approved'"
        args = []
        if platform:
            q += " AND platform=?"
            args.append(platform)
        q += " ORDER BY created ASC"
        return [dict(r) for r in conn.execute(q, args).fetchall()]


def get_queued(platform: str = None) -> list:
    with get_conn() as conn:
        q = "SELECT * FROM posts WHERE status='queued'"
        args = []
        if platform:
            q += " AND platform=?"
            args.append(platform)
        q += " ORDER BY scheduled_at ASC NULLS FIRST"
        return [dict(r) for r in conn.execute(q, args).fetchall()]


def get_stats() -> dict:
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT platform, status, COUNT(*) as n
            FROM posts GROUP BY platform, status
        """).fetchall()
        stats = {}
        for r in rows:
            stats.setdefault(r["platform"], {})[r["status"]] = r["n"]
        return stats
