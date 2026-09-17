"""Dispatches history/analytics calls to either the local SQLite backend or MongoDB Atlas,
depending on whether a MongoDB connection string is configured in Cài đặt. Every other
module calls functions here — never sqlite_history_store or mongo_store directly — so
switching backends never requires touching a call site.

Writes (add_content/add_image/add_video/add_post/add_token_usage) run fire-and-forget on a
background thread: history is a best-effort audit trail, so a slow or unreachable MongoDB
Atlas cluster must never freeze the UI or block content/image/video generation or posting.
Reads (dashboard_stats/list_recent) run synchronously and let failures propagate — the
app's global exception hook then shows a clear error instead of silently displaying
zeroed-out or stale numbers.
"""
from __future__ import annotations

import threading
import traceback

from app import config
from app.storage import mongo_store, sqlite_history_store


def _using_mongo() -> bool:
    return bool(config.get_secret("mongodb_uri"))


def _backend():
    return mongo_store if _using_mongo() else sqlite_history_store


def _fire_and_forget(fn, *args, **kwargs) -> None:
    def run() -> None:
        try:
            fn(*args, **kwargs)
        except Exception:  # noqa: BLE001 - a failed history write must never surface to the UI
            traceback.print_exc()

    threading.Thread(target=run, daemon=True).start()


def init_db() -> None:
    backend = _backend()
    try:
        backend.init_db()
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        if backend is mongo_store:
            sqlite_history_store.init_db()


def get_prompt(key: str) -> str | None:
    """Blocking read: run in a worker and report DB errors to the caller."""
    return _backend().get_prompt(key)


def save_prompt(key: str, text: str) -> None:
    """Acknowledged write: never report success before the DB has saved the prompt."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Prompt không được để trống.")
    _backend().save_prompt(key, text)


def add_content(topic: str, text: str) -> None:
    _fire_and_forget(_backend().add_content, topic, text)


def add_image(prompt: str, file_path: str) -> None:
    _fire_and_forget(_backend().add_image, prompt, file_path)


def add_video(script: str, file_path: str) -> None:
    _fire_and_forget(_backend().add_video, script, file_path)


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
    _fire_and_forget(
        _backend().add_post,
        post_type,
        message,
        attachment_path,
        scheduled_time,
        facebook_post_id,
        page_id,
        page_name,
        ok,
    )


def add_token_usage(
    provider: str, model: str, operation: str, input_tokens: int = 0, output_tokens: int = 0
) -> None:
    _fire_and_forget(_backend().add_token_usage, provider, model, operation, input_tokens, output_tokens)


def dashboard_stats() -> dict:
    return _backend().dashboard_stats()


def list_recent(table: str, limit: int = 20) -> list:
    return _backend().list_recent(table, limit)


def delete_item(table: str, item_id) -> None:
    """Remove one history record. Runs synchronously (unlike the add_* writes above) so the
    caller can confirm the delete actually happened before updating the gallery UI."""
    _backend().delete_item(table, item_id)
