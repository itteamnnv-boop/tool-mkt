"""App configuration: non-secret settings in a local JSON file, secrets in the OS keyring."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import keyring

APP_NAME = "ClaudeContentStudio"
KEYRING_SERVICE = "ClaudeContentStudio"

SECRET_KEYS = [
    "anthropic_api_key",
    "openai_api_key",
    "heygen_api_key",
    "grok_api_key",
    "facebook_app_secret",
    "tiktok_client_secret",
    "tiktok_access_token",
    "tiktok_refresh_token",
    "youtube_client_secret",
    "youtube_access_token",
    "youtube_refresh_token",
    "mongodb_uri",  # connection string (may embed a username/password) — kept out of config.json
]

# Legacy single-page secret from before multi-page support. Only read during migration.
_LEGACY_FB_TOKEN_KEY = "facebook_page_access_token"

DEFAULT_SETTINGS: dict[str, Any] = {
    "content_provider": "claude",
    "claude_model": "claude-sonnet-5",
    "openai_text_model": "gpt-4o-mini",
    "openai_image_model": "gpt-image-1",
    "heygen_avatar_id": "",
    "heygen_voice_id": "",
    "video_provider": "heygen",  # "heygen" (avatar nói) | "grok" (text-to-video)
    "grok_aspect_ratio": "16:9",
    "grok_resolution": "720p",
    "grok_duration": 6,
    "facebook_app_id": "",
    "facebook_pages": [],  # [{"id": ..., "name": ..., "category": ...}, ...] — tokens live in keyring
    "tiktok_client_key": "",
    "tiktok_display_name": "",
    "tiktok_open_id": "",
    "tiktok_avatar_url": "",
    "tiktok_token_expires_at": 0,  # epoch seconds — access_token, refresh_token live in keyring
    "youtube_client_id": "",
    "youtube_channel_title": "",
    "youtube_channel_id": "",
    "youtube_token_expires_at": 0,  # epoch seconds — access_token, refresh_token live in keyring
    # Defaults for the "Tự động hoá" pipeline, edited from its own settings dialog.
    "automation_tone": "thân thiện, chuyên nghiệp",
    "automation_hashtags": True,
    "automation_attachment": "image",  # "none" | "image" | "video"
    "automation_auto_post": False,  # when True, skip the manual review/confirm step and post right away
    "mongodb_database": "claude_content_studio",  # only used when the mongodb_uri secret is set
}


def app_data_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    d = Path(base) / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def _settings_path() -> Path:
    return app_data_dir() / "config.json"


def load_settings() -> dict[str, Any]:
    path = _settings_path()
    if not path.exists():
        return dict(DEFAULT_SETTINGS)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return dict(DEFAULT_SETTINGS)
    merged = dict(DEFAULT_SETTINGS)
    merged.update(data)
    return merged


def save_settings(settings: dict[str, Any]) -> None:
    path = _settings_path()
    path.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")


def get_secret(name: str) -> str:
    if name not in SECRET_KEYS:
        raise ValueError(f"Unknown secret key: {name}")
    return keyring.get_password(KEYRING_SERVICE, name) or ""


def set_secret(name: str, value: str) -> None:
    if name not in SECRET_KEYS:
        raise ValueError(f"Unknown secret key: {name}")
    if value:
        keyring.set_password(KEYRING_SERVICE, name, value)
    else:
        try:
            keyring.delete_password(KEYRING_SERVICE, name)
        except keyring.errors.PasswordDeleteError:
            pass


def output_dir(subfolder: str) -> Path:
    d = Path(__file__).resolve().parent.parent / "output" / subfolder
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------- Multi-page Facebook management ----------
# Each connected Page's non-secret info (id/name/category) lives in config.json under
# "facebook_pages"; each Page's own access token lives in the OS keyring, keyed by Page ID,
# so posting to N pages never requires juggling N plaintext tokens.


def list_pages() -> list[dict]:
    return load_settings().get("facebook_pages", [])


def save_pages(pages: list[dict]) -> None:
    settings = load_settings()
    settings["facebook_pages"] = pages
    save_settings(settings)


def upsert_pages(pages: list[dict]) -> None:
    """Merge newly-fetched pages into the stored list (matched by id), keeping existing order."""
    existing = list_pages()
    by_id = {p["id"]: p for p in existing}
    for page in pages:
        by_id[page["id"]] = {"id": page["id"], "name": page.get("name", page["id"]), "category": page.get("category", "")}
    save_pages(list(by_id.values()))


def remove_page(page_id: str) -> None:
    save_pages([p for p in list_pages() if p["id"] != page_id])
    delete_page_token(page_id)


def _page_token_key(page_id: str) -> str:
    return f"fb_page_token::{page_id}"


def get_page_token(page_id: str) -> str:
    return keyring.get_password(KEYRING_SERVICE, _page_token_key(page_id)) or ""


def set_page_token(page_id: str, token: str) -> None:
    keyring.set_password(KEYRING_SERVICE, _page_token_key(page_id), token)


def delete_page_token(page_id: str) -> None:
    try:
        keyring.delete_password(KEYRING_SERVICE, _page_token_key(page_id))
    except keyring.errors.PasswordDeleteError:
        pass


def migrate_legacy_facebook_config() -> None:
    """One-time upgrade from the old single-page (facebook_page_id + one token) setup."""
    if list_pages():
        return
    settings = load_settings()
    legacy_page_id = settings.get("facebook_page_id", "")
    legacy_token = keyring.get_password(KEYRING_SERVICE, _LEGACY_FB_TOKEN_KEY) or ""
    if not legacy_page_id or not legacy_token:
        return

    legacy_name = settings.get("facebook_page_name") or legacy_page_id
    settings["facebook_pages"] = [{"id": legacy_page_id, "name": legacy_name, "category": ""}]
    settings.pop("facebook_page_id", None)
    settings.pop("facebook_page_name", None)
    save_settings(settings)
    set_page_token(legacy_page_id, legacy_token)

    try:
        keyring.delete_password(KEYRING_SERVICE, _LEGACY_FB_TOKEN_KEY)
    except keyring.errors.PasswordDeleteError:
        pass


# ---------- TikTok account (single account — access/refresh tokens live in keyring) ----------


def get_tiktok_account() -> dict:
    settings = load_settings()
    return {
        "display_name": settings.get("tiktok_display_name", ""),
        "open_id": settings.get("tiktok_open_id", ""),
        "avatar_url": settings.get("tiktok_avatar_url", ""),
        "token_expires_at": settings.get("tiktok_token_expires_at", 0),
        "access_token": get_secret("tiktok_access_token"),
        "refresh_token": get_secret("tiktok_refresh_token"),
    }


def save_tiktok_account(
    display_name: str, open_id: str, avatar_url: str, access_token: str, refresh_token: str, expires_at: float
) -> None:
    settings = load_settings()
    settings["tiktok_display_name"] = display_name
    settings["tiktok_open_id"] = open_id
    settings["tiktok_avatar_url"] = avatar_url
    settings["tiktok_token_expires_at"] = expires_at
    save_settings(settings)
    set_secret("tiktok_access_token", access_token)
    set_secret("tiktok_refresh_token", refresh_token)


def clear_tiktok_account() -> None:
    settings = load_settings()
    settings["tiktok_display_name"] = ""
    settings["tiktok_open_id"] = ""
    settings["tiktok_avatar_url"] = ""
    settings["tiktok_token_expires_at"] = 0
    save_settings(settings)
    set_secret("tiktok_access_token", "")
    set_secret("tiktok_refresh_token", "")


# ---------- YouTube account (single channel — access/refresh tokens live in keyring) ----------


def get_youtube_account() -> dict:
    settings = load_settings()
    return {
        "channel_title": settings.get("youtube_channel_title", ""),
        "channel_id": settings.get("youtube_channel_id", ""),
        "token_expires_at": settings.get("youtube_token_expires_at", 0),
        "access_token": get_secret("youtube_access_token"),
        "refresh_token": get_secret("youtube_refresh_token"),
    }


def save_youtube_account(
    channel_title: str, channel_id: str, access_token: str, refresh_token: str, expires_at: float
) -> None:
    settings = load_settings()
    settings["youtube_channel_title"] = channel_title
    settings["youtube_channel_id"] = channel_id
    settings["youtube_token_expires_at"] = expires_at
    save_settings(settings)
    set_secret("youtube_access_token", access_token)
    if refresh_token:
        # Google only returns a refresh_token on first consent — refreshing an access_token
        # never returns a new one, so callers pass "" here to mean "keep the existing one".
        set_secret("youtube_refresh_token", refresh_token)


def clear_youtube_account() -> None:
    settings = load_settings()
    settings["youtube_channel_title"] = ""
    settings["youtube_channel_id"] = ""
    settings["youtube_token_expires_at"] = 0
    save_settings(settings)
    set_secret("youtube_access_token", "")
    set_secret("youtube_refresh_token", "")
