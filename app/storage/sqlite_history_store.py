"""Local SQLite backend for history/analytics data — used when no MongoDB URI is configured.
Selected automatically by history_store.py; call functions there, not this module directly."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from app.config import app_data_dir

SCHEMA = """
CREATE TABLE IF NOT EXISTS contents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    topic TEXT,
    text TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS images (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    prompt TEXT,
    file_path TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS videos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    script TEXT,
    file_path TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    post_type TEXT NOT NULL,
    message TEXT,
    attachment_path TEXT,
    scheduled_time TEXT,
    facebook_post_id TEXT,
    page_id TEXT DEFAULT '',
    page_name TEXT DEFAULT '',
    ok INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS token_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    operation TEXT NOT NULL,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0
);
"""


def _db_path() -> Path:
    return app_data_dir() / "history.sqlite3"


@contextmanager
def _connect():
    conn = sqlite3.connect(_db_path())
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with _connect() as conn:
        conn.executescript(SCHEMA)
        _ensure_column(conn, "posts", "page_id", "TEXT DEFAULT ''")
        _ensure_column(conn, "posts", "page_name", "TEXT DEFAULT ''")
        _ensure_column(conn, "posts", "ok", "INTEGER DEFAULT 1")


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, decl: str) -> None:
    """Adds a column to an existing table created by an older version of this app."""
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")


def add_content(topic: str, text: str) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO contents (created_at, topic, text) VALUES (?, ?, ?)",
            (datetime.now().isoformat(timespec="seconds"), topic, text),
        )


def add_image(prompt: str, file_path: str) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO images (created_at, prompt, file_path) VALUES (?, ?, ?)",
            (datetime.now().isoformat(timespec="seconds"), prompt, file_path),
        )


def add_video(script: str, file_path: str) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO videos (created_at, script, file_path) VALUES (?, ?, ?)",
            (datetime.now().isoformat(timespec="seconds"), script, file_path),
        )


def add_post(
    post_type: str,
    message: str,
    attachment_path: str = "",
    scheduled_time: str = "",
    facebook_post_id: str = "",
    page_id: str = "",
    page_name: str = "",
    ok: bool = True,
) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO posts (created_at, post_type, message, attachment_path, scheduled_time, "
            "facebook_post_id, page_id, page_name, ok) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                datetime.now().isoformat(timespec="seconds"),
                post_type,
                message,
                attachment_path,
                scheduled_time,
                facebook_post_id,
                page_id,
                page_name,
                1 if ok else 0,
            ),
        )


def add_token_usage(
    provider: str, model: str, operation: str, input_tokens: int = 0, output_tokens: int = 0
) -> None:
    """Store provider-reported token counts; never estimate missing usage."""
    with _connect() as conn:
        conn.execute(
            "INSERT INTO token_usage (created_at, provider, model, operation, input_tokens, output_tokens) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                datetime.now().isoformat(timespec="seconds"), provider, model, operation,
                max(0, int(input_tokens or 0)), max(0, int(output_tokens or 0)),
            ),
        )


def dashboard_stats() -> dict:
    """Return all-time and today's production numbers for the dashboard."""
    init_db()
    today = datetime.now().date().isoformat()
    with _connect() as conn:
        def count(table: str, where: str = "", params: tuple = ()) -> int:
            return int(conn.execute(f"SELECT COUNT(*) FROM {table} {where}", params).fetchone()[0])

        totals = {
            "contents": count("contents"),
            "images": count("images"),
            "videos": count("videos"),
            "posts": count("posts", "WHERE ok = 1"),
        }
        today_totals = {
            "contents": count("contents", "WHERE date(created_at) = ?", (today,)),
            "images": count("images", "WHERE date(created_at) = ?", (today,)),
            "videos": count("videos", "WHERE date(created_at) = ?", (today,)),
            "posts": count("posts", "WHERE ok = 1 AND date(created_at) = ?", (today,)),
        }
        usage = conn.execute(
            "SELECT COALESCE(SUM(input_tokens), 0), COALESCE(SUM(output_tokens), 0), COUNT(*) FROM token_usage"
        ).fetchone()
        providers = conn.execute(
            "SELECT provider, model, SUM(input_tokens), SUM(output_tokens), COUNT(*) "
            "FROM token_usage GROUP BY provider, model ORDER BY COUNT(*) DESC"
        ).fetchall()
    return {
        "totals": totals,
        "today": today_totals,
        "input_tokens": int(usage[0]),
        "output_tokens": int(usage[1]),
        "token_requests": int(usage[2]),
        "providers": providers,
    }


def list_recent(table: str, limit: int = 20) -> list[sqlite3.Row]:
    if table not in {"contents", "images", "videos", "posts"}:
        raise ValueError(f"Unknown table: {table}")
    with _connect() as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(f"SELECT * FROM {table} ORDER BY id DESC LIMIT ?", (limit,))
        return cur.fetchall()


def delete_item(table: str, item_id: int) -> None:
    if table not in {"contents", "images", "videos", "posts"}:
        raise ValueError(f"Unknown table: {table}")
    with _connect() as conn:
        conn.execute(f"DELETE FROM {table} WHERE id = ?", (item_id,))
