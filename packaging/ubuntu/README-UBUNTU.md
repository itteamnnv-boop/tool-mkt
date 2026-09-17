# Claude Content Studio cho Ubuntu

Gói cài đặt mã nguồn dành cho **Ubuntu Desktop 24.04 LTS 64-bit** (Intel/AMD hoặc ARM64).
Ubuntu 22.04 trên Intel/AMD cũng đáp ứng yêu cầu tối thiểu của Qt trong gói này.
Cần Internet ở lần cài đầu để tải thư viện Python và gói hệ thống; các tính năng AI/đăng bài
cần Internet cùng API key/tài khoản của bạn. Gói không chứa API key hay dữ liệu từ máy đóng gói.

## Cài đặt

Giải nén và chạy bằng tài khoản đang đăng nhập desktop, **không thêm sudo trước install.sh**:

```bash
tar -xzf claude-content-studio-ubuntu-1.0.0.tar.gz
cd claude-content-studio-ubuntu-1.0.0
bash install.sh
```

Script sẽ yêu cầu mật khẩu sudo khi cài các thư viện hệ thống bằng apt. Các thư viện Python
được cài vào virtualenv riêng, không thay đổi Python hệ thống. Shortcut chỉ được tạo sau khi
pip cài thành công và kiểm tra các phụ thuộc. Có thể xóa thư mục giải nén sau khi cài.
Nếu đã có đủ thư viện hệ thống, dùng `bash install.sh --skip-system-deps`.

## Mở ứng dụng

Mở **Claude Content Studio** trong Applications hoặc chạy:

```bash
~/.local/bin/claude-content-studio
```

Trong **Cài đặt**, nhập API key của bạn và chọn **Liquid Glass** hoặc **Crystal Glass**.
Nút, chữ, icon, card và padding đã được đưa vào gói cùng tất cả các trang chức năng.
Hướng dẫn kết nối các dịch vụ nằm trong `README.md`.

API key/token được lưu trong kho mật khẩu hệ thống qua keyring/Secret Service trên Ubuntu.
Ứng dụng cần một phiên desktop có D-Bus và kho mật khẩu đăng nhập đã được mở khóa;
không chạy app bằng sudo hoặc từ SSH không có desktop. Nếu vừa cài GNOME Keyring lần đầu,
đăng xuất rồi đăng nhập lại trước khi mở ứng dụng.

## Theme kính trên Ubuntu

Ubuntu không dùng Windows Acrylic. Gói giữ hiệu ứng viền kính, màu, độ trong suốt của các
control và dùng nền gradient để chữ vẫn đọc được khi compositor không cung cấp blur.
Hiệu ứng làm mờ wallpaper thật phụ thuộc desktop/compositor; không thể bảo đảm giống 100%
Windows trên mọi desktop Ubuntu. Nếu compositor đã được cấu hình blur, có thể bật nền trong suốt:

```bash
CLAUDE_STUDIO_TRANSPARENT=1 ~/.local/bin/claude-content-studio
```

## Thư mục và cập nhật

Mặc định:

- Ứng dụng và virtualenv: `~/.local/share/claude-content-studio/`.
- Cấu hình, SQLite và ảnh/video: `~/.local/share/ClaudeContentStudio/`.
- Lệnh khởi chạy: `~/.local/bin/claude-content-studio`.
- Shortcut: `~/.local/share/applications/claude-content-studio.desktop`.

Hỗ trợ `XDG_DATA_HOME` là đường dẫn tuyệt đối. Nếu trước đây đã chạy app trên Linux và có
`~/ClaudeContentStudio/config.json` hoặc `history.sqlite3`, app tiếp tục dùng thư mục cũ.
Ảnh/video cũ vẫn được mở theo đường dẫn đã lưu trong lịch sử; dữ liệu cũ không bị di chuyển.
API key trên Windows không được chuyển sang Ubuntu, cần nhập lại.
Để cập nhật, đóng app rồi chạy bộ cài của gói mới; cấu hình và dữ liệu được giữ lại.

## Chẩn đoán

```bash
~/.local/bin/claude-content-studio --diagnose
```

Lệnh in phiên bản Python/Qt và backend keyring, không đọc hay in API key/token.
Nếu báo lỗi keyring, kiểm tra phiên đăng nhập và mở khóa kho **Login** trong ứng dụng
**Passwords and Keys** (`seahorse`, có thể cài bằng `sudo apt install seahorse`).
Nếu báo thiếu plugin xcb, chạy lại `bash install.sh` để cài các thư viện hệ thống.
Muốn xem lỗi chi tiết, chạy ứng dụng từ terminal bằng lệnh ở trên.
Muốn mở MP4, cần trình phát video mặc định của desktop; có thể dùng VLC.

Kiểm tra giao diện offline từ thư mục giải nén (dữ liệu và API key đều được giả lập):

```bash
~/.local/share/claude-content-studio/venv/bin/python tools/ui_smoke.py
```

## Gỡ ứng dụng

```bash
bash ~/.local/share/claude-content-studio/uninstall.sh
```

Gỡ chương trình, virtualenv và shortcut; giữ nguyên cấu hình, lịch sử, ảnh/video và các
API key/token trong kho mật khẩu. Nếu đặt `XDG_DATA_HOME` khi cài, dùng cùng giá trị khi gỡ.

## Gói .deb (thay thế cho tar.gz)

`python tools/package_deb.py` (chạy được cả trên Windows) tạo `dist/claude-content-studio_1.0.0_all.deb` —
đóng gói cùng bộ file như tar.gz ở trên nhưng ở định dạng `.deb`, cài bằng:

```bash
sudo apt install ./claude-content-studio_1.0.0_all.deb
```

apt tự cài các thư viện hệ thống (khai báo trong `Depends`), sau đó `postinst` tự tạo virtualenv
riêng tại `/opt/claude-content-studio` và cài các gói Python — không cần chạy `install.sh` thủ công.
Gỡ bằng `sudo apt remove claude-content-studio` (giữ dữ liệu/API key) hoặc thêm `--purge` để xoá cả
`/opt/claude-content-studio`; dữ liệu người dùng trong `~/.local/share/ClaudeContentStudio` không bị
xoá ở cả hai trường hợp. File `.deb` này được ghép thủ công bằng Python (không dùng `dpkg-deb`/`ar`)
nên build được từ Windows, nhưng **chưa được cài thử bằng `apt`/`dpkg` thật trên Ubuntu** — nên kiểm
tra trên máy Ubuntu thật trước khi phát cho người khác dùng.

## Thông tin gói

Đây là bộ cài Python/Qt, không phải binary Linux độc lập hay AppImage. Các phiên bản
phụ thuộc trực tiếp được cố định trong `requirements.txt` của gói. `SHA256SUMS` kiểm tra
các file sau giải nén; file `.tar.gz.sha256` bên cạnh kiểm tra toàn bộ archive.
Gói được tạo trên Windows: đã kiểm tra giao diện offline, tính toàn vẹn archive và logic
bộ cài; chưa chạy kiểm thử thực tế trên Ubuntu.

Tài liệu phụ thuộc chính thức: [Qt Linux requirements](https://doc.qt.io/qt-6/linux-requirements.html),
[keyring trên Linux](https://keyring.readthedocs.io/en/stable/),
[các wheel PySide6](https://pypi.org/project/PySide6/6.11.2/).
