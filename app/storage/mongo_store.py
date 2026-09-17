"""MongoDB Atlas backend for history/analytics data — used when a MongoDB URI is
configured in Cài đặt. Selected automatically by history_store.py; call functions there,
not this module directly.

Collection names mirror the SQLite table names (contents/images/videos/posts/token_usage)
so the two backends store the same shape of data. Documents use Mongo's native `_id`
(roughly time-ordered) instead of a SQLite autoincrement id, and `created_at` is stored as
a real BSON datetime so dashboard_stats() can do proper date-range queries.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from pymongo import MongoClient
from pymongo.database import Database

from app import config

_client: MongoClient | None = None
_client_uri: str | None = None

# Keep server selection short — this backend is used from UI-thread callers too, and a
# slow/unreachable Atlas cluster should fail fast rather than freeze the app.
_TIMEOUT_MS = 5000


def _get_db() -> Database:
    global _client, _client_uri
    uri = config.get_secret("mongodb_uri")
    if not uri:
        raise ValueError("Chưa cấu hình MongoDB connection string trong Cài đặt.")
    if _client is None or _client_uri != uri:
        if _client is not None:
            _client.close()
        _client = MongoClient(uri, serverSelectionTimeoutMS=_TIMEOUT_MS)
        _client_uri = uri
    db_name = config.load_settings().get("mongodb_database") or "claude_content_studio"
    return _client[db_name]


def init_db() -> None:
    # No schema to create — Mongo collections/indexes are created on first write.
    # Just verify the connection is reachable so startup surfaces bad config early.
    _get_db().client.admin.command("ping")


def get_prompt(key: str) -> str | None:
    document = _get_db()["prompts"].find_one({"_id": key})
    return document["text"] if document else None


def save_prompt(key: str, text: str) -> None:
    _get_db()["prompts"].update_one(
        {"_id": key}, {"$set": {"text": text, "updated_at": datetime.now()}}, upsert=True
    )


def add_content(topic: str, text: str) -> None:
    _get_db()["contents"].insert_one({"created_at": datetime.now(), "topic": topic, "text": text})


def add_image(prompt: str, file_path: str) -> None:
    _get_db()["images"].insert_one({"created_at": datetime.now(), "prompt": prompt, "file_path": file_path})


def add_video(script: str, file_path: str) -> None:
    _get_db()["videos"].insert_one({"created_at": datetime.now(), "script": script, "file_path": file_path})


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
    _get_db()["posts"].insert_one(
        {
            "created_at": datetime.now(),
            "post_type": post_type,
            "message": message,
            "attachment_path": attachment_path,
            "scheduled_time": scheduled_time,
            "facebook_post_id": facebook_post_id,
            "page_id": page_id,
            "page_name": page_name,
            "ok": bool(ok),
        }
    )


def add_token_usage(
    provider: str, model: str, operation: str, input_tokens: int = 0, output_tokens: int = 0
) -> None:
    _get_db()["token_usage"].insert_one(
        {
            "created_at": datetime.now(),
            "provider": provider,
            "model": model,
            "operation": operation,
            "input_tokens": max(0, int(input_tokens or 0)),
            "output_tokens": max(0, int(output_tokens or 0)),
        }
    )


def dashboard_stats() -> dict:
    db = _get_db()
    today_start = datetime.combine(datetime.now().date(), datetime.min.time())
    tomorrow_start = today_start + timedelta(days=1)
    today_range = {"created_at": {"$gte": today_start, "$lt": tomorrow_start}}

    def count(collection: str, extra_filter: dict | None = None) -> int:
        return db[collection].count_documents(dict(extra_filter or {}))

    totals = {
        "contents": count("contents"),
        "images": count("images"),
        "videos": count("videos"),
        "posts": count("posts", {"ok": True}),
    }
    today_totals = {
        "contents": count("contents", today_range),
        "images": count("images", today_range),
        "videos": count("videos", today_range),
        "posts": count("posts", {"ok": True, **today_range}),
    }

    usage_result = list(
        db["token_usage"].aggregate(
            [{"$group": {"_id": None, "input": {"$sum": "$input_tokens"}, "output": {"$sum": "$output_tokens"}, "count": {"$sum": 1}}}]
        )
    )
    input_tokens = usage_result[0]["input"] if usage_result else 0
    output_tokens = usage_result[0]["output"] if usage_result else 0
    token_requests = usage_result[0]["count"] if usage_result else 0

    providers_result = list(
        db["token_usage"].aggregate(
            [
                {
                    "$group": {
                        "_id": {"provider": "$provider", "model": "$model"},
                        "input": {"$sum": "$input_tokens"},
                        "output": {"$sum": "$output_tokens"},
                        "count": {"$sum": 1},
                    }
                },
                {"$sort": {"count": -1}},
            ]
        )
    )
    providers = [
        (p["_id"]["provider"], p["_id"]["model"], p["input"], p["output"], p["count"]) for p in providers_result
    ]

    return {
        "totals": totals,
        "today": today_totals,
        "input_tokens": int(input_tokens),
        "output_tokens": int(output_tokens),
        "token_requests": int(token_requests),
        "providers": providers,
    }


def list_recent(table: str, limit: int = 20) -> list[dict]:
    if table not in {"contents", "images", "videos", "posts"}:
        raise ValueError(f"Unknown table: {table}")
    return list(_get_db()[table].find().sort("_id", -1).limit(limit))


def delete_item(table: str, item_id) -> None:
    if table not in {"contents", "images", "videos", "posts"}:
        raise ValueError(f"Unknown table: {table}")
    _get_db()[table].delete_one({"_id": item_id})
