"""Vision-labelled objects with locally refined, editable pixel masks."""
import base64
from dataclasses import dataclass
import json
import math
from pathlib import Path

from openai import OpenAI
from PySide6.QtCore import QBuffer, QIODevice, QRectF, Qt
from PySide6.QtGui import QImage, QPainter

from app.storage import history_store


@dataclass
class ImageLayer:
    name: str
    description: str
    mask: QImage  # selected pixels are opaque; everything else is transparent
    rect: QRectF
    area: int
    refined: bool = True

    def contains(self, point):
        if not (0 <= point.x() < self.mask.width() and 0 <= point.y() < self.mask.height()):
            return False
        x, y = int(point.x()), int(point.y())
        return 0 <= x < self.mask.width() and 0 <= y < self.mask.height() and self.mask.pixelColor(x, y).alpha() > 127

    def cutout(self, image):
        if self.rect.isEmpty():
            return QImage()
        result = image.convertToFormat(QImage.Format.Format_ARGB32)
        painter = QPainter(result)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
        painter.drawImage(0, 0, self.mask)
        painter.end()
        return result.copy(self.rect.toAlignedRect().intersected(result.rect()))

    def update_geometry(self):
        import cv2
        import numpy as np
        rgba = self.mask.convertToFormat(QImage.Format.Format_RGBA8888)
        pixels = np.frombuffer(rgba.bits(), np.uint8).reshape(rgba.height(), rgba.bytesPerLine())
        alpha = pixels[:, :rgba.width() * 4].reshape(rgba.height(), rgba.width(), 4)[:, :, 3]
        selected = (alpha > 127).astype(np.uint8)
        self.area = int(np.count_nonzero(selected))
        self.rect = QRectF(*cv2.boundingRect(selected))

    def position_text(self):
        r = self.rect
        return f"x={r.x():.0f}, y={r.y():.0f}, rộng={r.width():.0f}, cao={r.height():.0f} px (gốc ở góc trên trái)"


def parse_objects(text):
    data = json.loads(text)
    if not isinstance(data, dict) or not isinstance(data.get("objects"), list):
        raise ValueError("AI chưa trả về danh sách lớp hợp lệ. Hãy phân tích lại.")
    result = []
    for obj in data["objects"][:24]:
        if not isinstance(obj, dict) or not isinstance(obj.get("name"), str):
            continue
        def read_polygons(key):
            result = []
            for polygon in obj.get(key, [])[:8] if isinstance(obj.get(key), list) else []:
                if not isinstance(polygon, list) or not 3 <= len(polygon) <= 128:
                    continue
                valid = all(isinstance(p, list) and len(p) == 2 and
                            all(type(v) in (int, float) and math.isfinite(v) and 0 <= v <= 1000 for v in p)
                            for p in polygon)
                if valid:
                    result.append(polygon)
            return result
        polygons = read_polygons("polygons")
        if polygons:
            result.append({"name": obj["name"][:100], "description": str(obj.get("description", ""))[:600],
                           "polygons": polygons, "holes": read_polygons("holes"),
                           "background": obj.get("background") is True})
    if not result:
        raise ValueError("Không tìm thấy lớp có đường biên hợp lệ. Hãy thử lại hoặc khoanh vùng thủ công.")
    return result


def refine_layers(image, objects, on_progress=None):
    try:
        import cv2
        import numpy as np
    except ImportError as exc:
        raise ValueError("Cần cài numpy và opencv-python-headless theo requirements.txt để tách lớp.") from exc
    small = image.scaled(min(1024, image.width()), min(1024, image.height()), Qt.AspectRatioMode.KeepAspectRatio,
                         Qt.TransformationMode.SmoothTransformation).convertToFormat(QImage.Format.Format_RGBA8888)
    h, w = small.height(), small.width()
    rgba = np.frombuffer(small.bits(), np.uint8).reshape(h, small.bytesPerLine())[:, :w * 4].reshape(h, w, 4)
    bgr = cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGR)
    def rasterize(polygons):
        mask = np.zeros((h, w), np.uint8)
        for polygon in polygons:
            points = np.array([[round(x * (w - 1) / 1000), round(y * (h - 1) / 1000)] for x, y in polygon], np.int32)
            cv2.fillPoly(mask, [points], 255)
        return mask

    seeds = []
    holes = []
    for obj in objects:
        seed = rasterize(obj["polygons"])
        hole = rasterize(obj.get("holes", []))
        seed[hole > 0] = 0
        seeds.append(seed)
        holes.append(hole)
    candidates = []
    for index, obj in enumerate(objects):
        if on_progress:
            on_progress(f"Đang tách lớp {index + 1}/{len(objects)}: {obj['name']}")
        seed = seeds[index].copy()
        excluded = holes[index].copy()
        # A surrounding wall/floor must never pin the subject as definite foreground.
        if obj.get("background", False):
            for j, other in enumerate(objects):
                if not other.get("background", False):
                    excluded = cv2.bitwise_or(excluded, seeds[j])
        seed[excluded > 0] = 0
        if np.count_nonzero(seed) < 5:
            continue
        kernel = np.ones((5, 5), np.uint8)
        outer = cv2.dilate(seed, kernel, iterations=3)
        outer[excluded > 0] = 0
        # Seed every disconnected piece independently; a large piece must not
        # erase a smaller one by imposing its distance threshold on all pieces.
        count, components = cv2.connectedComponents(seed)
        inner = np.zeros_like(seed)
        for component in range(1, count):
            part = (components == component).astype(np.uint8)
            distance = cv2.distanceTransform(np.pad(part, 1), cv2.DIST_L2, 5)[1:-1, 1:-1]
            peak = float(distance.max())
            if peak:
                inner[distance >= max(1.0, peak * 0.8)] = 255
        labels = np.full((h, w), cv2.GC_BGD, np.uint8)
        labels[outer > 0] = cv2.GC_PR_BGD
        labels[seed > 0] = cv2.GC_PR_FGD
        labels[inner > 0] = cv2.GC_FGD
        labels[excluded > 0] = cv2.GC_BGD
        refined = False
        selected = seed
        if np.any(inner) and np.any(outer == 0):
            try:
                cv2.grabCut(bgr, labels, None, np.zeros((1, 65)), np.zeros((1, 65)), 3, cv2.GC_INIT_WITH_MASK)
                candidate = np.where((labels == cv2.GC_FGD) | (labels == cv2.GC_PR_FGD), 255, 0).astype(np.uint8)
                if np.count_nonzero(candidate) >= 5:
                    selected, refined = candidate, True
            except cv2.error:
                pass  # retain the explicit AI contour, flagged as approximate
        selected[excluded > 0] = 0
        candidates.append((index, selected, refined))

    # Assign each visible pixel once, with small objects before broad surfaces.
    # Preserve the original display order; ownership must not depend on JSON order.
    claimed = np.zeros((h, w), np.uint8)
    resolved = {}
    for index, selected, refined in sorted(candidates, key=lambda entry: (
            bool(objects[entry[0]].get("background", False)), np.count_nonzero(entry[1]),
            objects[entry[0]]["name"])):
        selected = selected.copy()
        original_area = np.count_nonzero(selected)
        selected[claimed > 0] = 0
        remaining = np.count_nonzero(selected)
        if remaining < 5:
            continue
        # Large conflicts are explicitly shown as needing review, not precise layers.
        refined = refined and remaining >= original_area * 0.8
        claimed[selected > 0] = 255
        resolved[index] = selected, refined
    layers = []
    for index, obj in enumerate(objects):
        if index not in resolved:
            continue
        selected, refined = resolved[index]
        full = cv2.resize(selected, (image.width(), image.height()), interpolation=cv2.INTER_NEAREST)
        pixels = np.full((image.height(), image.width(), 4), 255, np.uint8)
        pixels[:, :, 3] = full
        mask = QImage(pixels.data, image.width(), image.height(), image.width() * 4, QImage.Format.Format_RGBA8888).copy()
        x, y, width, height = cv2.boundingRect(full)
        layers.append(ImageLayer(obj["name"], obj["description"], mask, QRectF(x, y, width, height),
                                 int(np.count_nonzero(full)), refined))
    if not layers:
        raise ValueError("Các vùng AI trả về quá nhỏ để tách lớp. Hãy thử lại.")
    return layers


DEFAULT_LAYER_MODEL = "gpt-5.4"
LAYER_MODELS = (("GPT-5.4 · Ưu tiên chất lượng", "gpt-5.4"),
                ("Grok 4.7 · xAI", "grok-4.7"),
                ("GPT-4o mini · Tiết kiệm", "gpt-4o-mini"))


class ImageLayerClient:
    def __init__(self, api_key, model=DEFAULT_LAYER_MODEL):
        self.provider = "Grok" if model.startswith("grok-") else "OpenAI"
        if not api_key:
            raise ValueError(f"Thiếu {self.provider} API key. Vào Cài đặt để nhập.")
        self.client = OpenAI(api_key=api_key, **({"base_url": "https://api.x.ai/v1"} if self.provider == "Grok" else {}))
        self.model = model

    def analyze(self, path: Path, on_progress=None):
        image = QImage(str(path))
        if image.isNull():
            raise ValueError("Không đọc được ảnh để phân tích lớp.")
        precise = self.model in {"gpt-5.4", "gpt-5.4-2026-03-05"}
        limit = 3072 if precise else 1536
        scaled = image.scaled(min(limit, image.width()), min(limit, image.height()),
                              Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        scaled.save(buffer, "PNG")
        uri = "data:image/png;base64," + base64.b64encode(bytes(buffer.data())).decode()
        if on_progress:
            on_progress(f"{self.model} đang nhận diện đồ vật và vị trí trong ảnh…")
        prompt = (
            "Analyze this image into separate editable visible objects/materials. Return ONLY JSON: "
            '{"objects":[{"name":"Vietnamese short name","description":"Vietnamese appearance and precise location",'
            '"background":false,"polygons":[[[x,y],[x,y],[x,y]]],"holes":[]} ]}. '
            "Coordinates normalized 0..1000, origin TOP LEFT, x right, y down. Trace visible silhouettes with "
            "16-80 vertices rather than bounding boxes. Up to 20 objects. First inspect the actual image; "
            "do not use a fixed inventory of clothing or body parts. Separate only visible materials. "
            "Distinguish a skirt or dress from trousers. Never invent shoes cropped out of the image. "
            "Never include a whole person over their parts. "
            "Use multiple polygons for disconnected visible portions. Put interior excluded areas in holes "
            "using the same polygon format: face inside hair, person in wall, gaps between limbs, etc. "
            "Set background=true for wall, floor, sky and other background surfaces only. "
            "All layers must be mutually exclusive visible surfaces; never trace a hidden part. "
            "Distinguish viewer-left and viewer-right instances in names. Identify only actually visible objects. "
            "Omit tiny or uncertain objects rather than inventing their contours. "
            "Check every contour against the image before returning it. A background polygon must not "
            "cover a person's hair, face, skin or clothing; exclude the entire visible silhouette as holes. "
            "All names and descriptions MUST be in Vietnamese. "
            f"The supplied image is {scaled.width()} by {scaled.height()} pixels, but ALL polygon coordinates "
            "must use the normalized 0..1000 range in BOTH axes, never raw pixels."
        )
        response = self.client.chat.completions.create(
            model=self.model, response_format={"type": "json_object"},
            **({"reasoning_effort": "high"} if precise else {}),
            messages=[{"role": "user", "content": [{"type": "text", "text": prompt},
                       {"type": "image_url", "image_url": {"url": uri, "detail": "original" if precise else "high"}}]}],
        )
        if response.usage:
            history_store.add_token_usage(self.provider, self.model, "phân tích lớp ảnh",
                                          response.usage.prompt_tokens, response.usage.completion_tokens)
        return refine_layers(image, parse_objects(response.choices[0].message.content or ""), on_progress)
