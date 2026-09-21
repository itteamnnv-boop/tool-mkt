"""Independent, durable copies of published media and a recovery manifest."""
import json
import shutil
from pathlib import Path
from uuid import uuid4

from app import config


def attachment_paths(row):
    value = row.get("attachment_path") or ""
    if not value:
        return []
    values = json.loads(value) if row.get("post_type") == "photos" else [value]
    if not isinstance(values, list) or any(not isinstance(p, str) for p in values):
        raise ValueError("Danh sách tệp đính kèm không hợp lệ.")
    return [Path(p) for p in values if p]


def snapshot(row):
    """Write the manifest last; incomplete copies must never look complete."""
    row = dict(row)
    folder = config.app_data_dir() / "published_posts" / uuid4().hex
    folder.mkdir(parents=True)
    paths = []
    for index, source in enumerate(attachment_paths(row)):
        target = folder / f"{index + 1:02d}_{source.name}"
        shutil.copy2(source, target)
        paths.append(str(target))
    row["attachment_path"] = (json.dumps(paths, ensure_ascii=False) if row["post_type"] == "photos"
                              else paths[0] if paths else "")
    (folder / "post.json").write_text(json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8")
    return row
