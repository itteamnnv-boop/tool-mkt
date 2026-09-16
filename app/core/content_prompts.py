"""Shared system/user prompt builders reused by every text-generation provider (Claude, OpenAI, ...)."""
from __future__ import annotations

SYSTEM_PROMPT_POST = (
    "Bạn là chuyên gia content marketing tiếng Việt, chuyên viết bài đăng Facebook "
    "cho fanpage doanh nghiệp. Viết ngắn gọn, hấp dẫn, đúng giọng điệu yêu cầu, "
    "có emoji phù hợp (không lạm dụng), có call-to-action rõ ràng ở cuối."
)
SYSTEM_PROMPT_IMAGE_PROMPT = "Bạn là chuyên gia viết prompt cho công cụ tạo ảnh AI."
SYSTEM_PROMPT_VIDEO_SCRIPT = "Bạn là biên kịch video quảng cáo ngắn."
SYSTEM_PROMPT_VIDEO_SCRIPT_FROM_REFERENCE = (
    "Bạn là biên kịch video quảng cáo ngắn, giỏi phân tích ý tưởng/cấu trúc/nhịp điệu từ "
    "một video mẫu rồi biến tấu thành kịch bản hoàn toàn mới — không sao chép nguyên văn "
    "để tránh vi phạm bản quyền."
)


def build_post_user_prompt(
    topic: str,
    tone: str,
    length: str,
    audience: str,
    include_hashtags: bool,
) -> str:
    return (
        f"Chủ đề: {topic}\n"
        f"Đối tượng đọc: {audience}\n"
        f"Giọng điệu: {tone}\n"
        f"Độ dài mong muốn: {length}\n"
        f"{'Thêm 3-5 hashtag liên quan ở cuối bài.' if include_hashtags else 'Không cần hashtag.'}\n\n"
        "Hãy viết nội dung bài đăng Facebook hoàn chỉnh, sẵn sàng đăng."
    )


def build_image_prompt_user_prompt(content_text: str) -> str:
    return (
        "Dựa trên nội dung bài đăng Facebook sau, hãy viết MỘT prompt tiếng Anh "
        "ngắn gọn (1-2 câu) để tạo ảnh minh họa bằng AI, mô tả rõ chủ thể, bối cảnh, "
        "phong cách hình ảnh. Chỉ trả về prompt, không thêm giải thích.\n\n"
        f"Nội dung bài đăng:\n{content_text}"
    )


def build_video_script_user_prompt(content_text: str) -> str:
    return (
        "Dựa trên nội dung bài đăng Facebook sau, hãy viết lại thành kịch bản lời thoại "
        "(tiếng Việt, giọng nói tự nhiên, 20-40 giây khi đọc) để một avatar AI đọc trong video "
        "quảng cáo. Chỉ trả về lời thoại, không thêm chú thích cảnh quay.\n\n"
        f"Nội dung bài đăng:\n{content_text}"
    )


def build_video_script_from_reference_user_prompt(transcript: str, content_text: str) -> str:
    context_block = (
        f"\nNội dung bài đăng Facebook liên quan (ngữ cảnh sản phẩm/thương hiệu, nếu có):\n{content_text}\n"
        if content_text.strip()
        else ""
    )
    return (
        "Dưới đây là lời thoại trích xuất (transcript) từ một video mẫu — chỉ dùng để THAM KHẢO "
        "ý tưởng, cấu trúc, nhịp điệu, KHÔNG được sao chép nguyên văn:\n"
        f"---\n{transcript}\n---\n"
        f"{context_block}\n"
        "Hãy viết MỘT kịch bản lời thoại mới (tiếng Việt, giọng nói tự nhiên, 20-40 giây khi đọc), "
        "lấy cảm hứng từ video mẫu trên nhưng nội dung hoàn toàn mới và phù hợp với ngữ cảnh sản phẩm/"
        "thương hiệu ở trên (nếu có). Chỉ trả về lời thoại, không thêm chú thích cảnh quay hay giải thích."
    )
