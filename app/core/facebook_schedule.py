"""Read and persist publication evidence; elapsed time alone is not success."""
import json
from datetime import datetime

from app import config
from app.core.facebook_client import FacebookClient, post_to_pages
from app.storage import history_store


def status_data(row):
    try:
        value = json.loads(row.get("schedule_status") or "{}")
        return value if isinstance(value, dict) else {}
    except (TypeError, ValueError):
        return {}


def local_time(value):
    if not value:
        return None
    try:
        if isinstance(value, (int, float)) or str(value).isdigit():
            return datetime.fromtimestamp(float(value)).astimezone()
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone()
    except (ValueError, TypeError, OverflowError, OSError):
        return None


def schedule_time(row):
    return local_time(status_data(row).get("scheduled_time") or row.get("scheduled_time"))


def status_label(row, now=None):
    state = status_data(row)
    if state.get("uncertain"):
        return "Chưa xác nhận — kiểm tra Page"
    if not row.get("ok"):
        return "Lên lịch thất bại"
    if state.get("published") is True:
        return "Đã đăng"
    if state.get("failed"):
        return "Facebook báo lỗi xử lý video"
    scheduled = schedule_time(row)
    if scheduled and scheduled <= (now or datetime.now().astimezone()):
        checked = local_time(state.get("checked_at"))
        if state.get("published") is False and checked and checked >= scheduled:
            return "Đã đến giờ — chưa đăng"
        return "Đã đến giờ — cần kiểm tra"
    if state.get("published") is False:
        return "Chờ đăng"
    return "Chờ đăng — chưa xác minh" if scheduled else "Chưa xác định"


def sync_posts(rows, on_progress=None):
    results = []
    for index, row in enumerate(rows):
        if not row.get("ok"):
            continue
        state = status_data(row)
        if on_progress:
            on_progress(f"Đang kiểm tra {index + 1}/{len(rows)} · {row.get('page_name') or row.get('page_id')}")
        token = ""
        try:
            page_id = row.get("page_id")
            token = config.get_page_token(page_id) if page_id else ""
            if not token:
                raise ValueError("Thiếu token Page. Kết nối lại Facebook để kiểm tra trạng thái.")
            data = FacebookClient(page_id, token).get_publication_status(row.get("facebook_post_id", ""), row["post_type"])
            if not isinstance(data.get("published"), bool):
                raise ValueError("Facebook chưa trả về trạng thái xuất bản; chưa thể xác minh.")
            video_status = data.get("video_status") or {}
            state.update(published=data["published"],
                         failed=video_status.get("video_status") == "error",
                         checked_at=datetime.now().astimezone().isoformat(timespec="seconds"), sync_error="")
            if data.get("message") is not None:
                state["message"] = data["message"]
            if local_time(data.get("scheduled_time")):
                state["scheduled_time"] = data["scheduled_time"]
        except Exception as exc:
            state["sync_error"] = str(exc).replace(token, "[token]") if token else str(exc)
        state["attempted_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
        try:
            history_store.save_schedule_status(row, state)
        except Exception as exc:
            state["sync_error"] = f"Không lưu được kết quả kiểm tra: {exc}"
        results.append(dict(row, schedule_status=json.dumps(state, ensure_ascii=False)))
    return results


def post_and_record(pages, post_type, content, attachment_path="", on_progress=None, **kwargs):
    # Save before the UI reports completion, including rejected schedule requests.
    results = post_to_pages(pages, post_type, on_progress=on_progress, **kwargs)
    scheduled = kwargs.get("scheduled_time")
    label = datetime.fromtimestamp(scheduled).astimezone().isoformat(timespec="minutes") if scheduled else ""
    for result in results:
        try:
            history_store.save_post(post_type, content, attachment_path, label, result.get("post_id", ""),
                                    result["id"], result["name"], result["ok"], error=result.get("error", ""),
                                    uncertain=result.get("uncertain", False), link_url=kwargs.get("link") or "")
        except Exception as exc:
            result["archive_error"] = str(exc)
    return results
