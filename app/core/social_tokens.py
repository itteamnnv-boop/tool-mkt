"""Shared access-token refresh for manual and automated publishing."""
import time
from app import config
from app.core.tiktok_client import refresh_access_token as refresh_tiktok
from app.core.youtube_client import refresh_access_token as refresh_youtube

def ensure_tiktok_token(on_progress=None) -> str:
    """Returns a still-valid TikTok access token, refreshing it first if it's expired or
    about to expire. Runs inside a worker thread — talks to config (keyring/JSON) directly,
    same pattern as the *_client modules that read config from their owning UI tab."""
    account = config.get_tiktok_account()
    access_token = account.get("access_token", "")
    if not access_token:
        raise ValueError("Chưa kết nối TikTok — vào tab 'Kết nối TikTok' trước.")

    expires_at = account.get("token_expires_at", 0) or 0
    if time.time() < expires_at - 300:  # still valid for 5+ more minutes
        return access_token

    if on_progress:
        on_progress("Access token TikTok sắp hết hạn, đang làm mới...")
    settings = config.load_settings()
    client_key = settings.get("tiktok_client_key", "")
    client_secret = config.get_secret("tiktok_client_secret")
    refresh_token = account.get("refresh_token", "")
    if not client_key or not client_secret or not refresh_token:
        raise ValueError("Token TikTok đã hết hạn — vào tab 'Kết nối TikTok' để đăng nhập lại.")

    tokens = refresh_tiktok(client_key, client_secret, refresh_token)
    config.save_tiktok_account(
        display_name=account.get("display_name", ""),
        open_id=account.get("open_id", ""),
        avatar_url=account.get("avatar_url", ""),
        access_token=tokens["access_token"],
        refresh_token=tokens.get("refresh_token") or refresh_token,
        expires_at=tokens.get("expires_at", 0),
    )
    return tokens["access_token"]



def ensure_youtube_token(on_progress=None) -> str:
    """Returns a still-valid YouTube access token, refreshing it first if it's expired or
    about to expire. Runs inside a worker thread — talks to config (keyring/JSON) directly,
    same pattern as tiktok_tab.py's _ensure_valid_token."""
    account = config.get_youtube_account()
    access_token = account.get("access_token", "")
    if not access_token:
        raise ValueError("Chưa kết nối YouTube — vào tab 'Kết nối YouTube' trước.")

    expires_at = account.get("token_expires_at", 0) or 0
    if time.time() < expires_at - 300:  # still valid for 5+ more minutes
        return access_token

    if on_progress:
        on_progress("Access token YouTube sắp hết hạn, đang làm mới...")
    settings = config.load_settings()
    client_id = settings.get("youtube_client_id", "")
    client_secret = config.get_secret("youtube_client_secret")
    refresh_token = account.get("refresh_token", "")
    if not client_id or not client_secret or not refresh_token:
        raise ValueError("Token YouTube đã hết hạn — vào tab 'Kết nối YouTube' để đăng nhập lại.")

    tokens = refresh_youtube(client_id, client_secret, refresh_token)
    config.save_youtube_account(
        channel_title=account.get("channel_title", ""),
        channel_id=account.get("channel_id", ""),
        access_token=tokens["access_token"],
        refresh_token=tokens.get("refresh_token", ""),  # "" means: keep the existing one, see config.py
        expires_at=tokens.get("expires_at", 0),
    )
    return tokens["access_token"]


