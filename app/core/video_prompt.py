"""Turn a script into production directions without changing its claims."""
from __future__ import annotations


def create_video_prompt(client, script: str, target: str, scene: str = "",
                        duration: int = 6, aspect_ratio: str = "16:9") -> str:
    if not script.strip():
        raise ValueError("Nhập kịch bản trước khi tạo prompt.")
    system = (
        "Bạn là đạo diễn video. Chuyển kịch bản thành chỉ dẫn sản xuất cụ thể bằng tiếng Việt. "
        "Bám sát thông điệp, đối tượng, sản phẩm và trình tự của kịch bản. Không bịa tên, giá, "
        "cam kết, công dụng hoặc thông tin liên hệ. Không thay đổi lời thoại. Chỉ trả về prompt "
        "sẵn dùng, không giải thích. Tách hướng dẫn hình ảnh khỏi lời thoại; không đọc hướng dẫn. "
        "Nêu bố cục, bối cảnh, ánh sáng, phong cách, biểu cảm, nhịp điệu và chuyển cảnh phù hợp. "
        "Không giả định đã nhìn thấy ảnh; ảnh vật liệu đính kèm là nguồn hình ảnh ưu tiên."
    )
    constraints = (
        "Dùng HeyGen Video Agent với avatar và voice cá nhân đã chọn. Giữ nguyên toàn bộ lời thoại; "
        "thời lượng đủ để đọc tự nhiên. Không tự chọn avatar/voice khác."
        if target == "heygen" else
        f"Dùng Grok, thời lượng {duration} giây, khung hình {aspect_ratio}. "
        "Chia nhịp cảnh khả thi trong thời lượng này; giữ nhân vật và sản phẩm nhất quán với ảnh vật liệu. "
        "Nếu lời thoại dài, không hứa đọc hết hay tự ý đổi thông điệp; ưu tiên thể hiện ý tưởng bằng hình ảnh."
    )
    result = client._complete(system, f"{constraints}\nBối cảnh bổ sung: {scene}\nKịch bản gốc:\n{script}",
                              max_tokens=1800, operation="prompt dựng video")
    if not result or not result.strip():
        raise RuntimeError("Chưa nhận được prompt. Hãy thử lại.")
    return result.strip()


def compose_video_prompt(directions: str, script: str) -> str:
    return (f"CHỈ DẪN DỰNG VIDEO (không đọc thành lời):\n{directions}\n\n"
            f"KỊCH BẢN GỐC — giữ nguyên thông điệp và lời thoại, không tự thêm thông tin:\n{script}")
