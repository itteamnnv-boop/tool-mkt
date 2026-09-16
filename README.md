# Claude Content Studio

Desktop app (Python + PySide6) dùng **Claude API làm lõi** để viết content, sinh ảnh (OpenAI),
sinh video avatar (HeyGen), rồi đăng thẳng lên Facebook Page (Graph API).

## 1. Cài đặt

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## 2. Lấy API key / token

### Anthropic (Claude)
1. Vào https://console.anthropic.com/ → **API Keys** → tạo key mới.

### OpenAI (tạo ảnh)
1. Vào https://platform.openai.com/api-keys → tạo key mới.
2. Cần có quyền dùng model ảnh (`gpt-image-1` hoặc `dall-e-3`).

### HeyGen (tạo video avatar)
1. Vào https://app.heygen.com/settings → mục **API Keys** (cần gói trả phí để dùng API).
2. Bạn cần có ít nhất 1 avatar (avatar có sẵn của HeyGen, hoặc avatar/digital twin của riêng bạn).

### Facebook — kết nối nhiều Page cùng lúc
App có tab riêng **"🔗 Kết nối Facebook"** để tự động lấy token của TẤT CẢ Page bạn quản lý chỉ từ
1 User Access Token, thay vì phải tự tìm từng Page Access Token thủ công.

1. (Tuỳ chọn) Tạo một Facebook App tại https://developers.facebook.com/apps/ (loại "Business").
   Vào app đó → **Cài đặt cơ bản** để lấy **App ID** và **App Secret**, dán vào mục **Cài đặt** của
   Claude Content Studio — chỉ dùng để tự động đổi token sang bản dài hạn, bỏ trống vẫn kết nối được
   nhưng token chỉ dùng được trong ~1-2 giờ.
2. Vào **Graph API Explorer** (https://developers.facebook.com/tools/explorer/):
   - Chọn App của bạn (hoặc dùng App Graph API Explorer mặc định nếu chưa tạo App riêng) → "Get User
     Access Token" với các quyền: `pages_show_list`, `pages_read_engagement`, `pages_manage_posts`.
   - Copy **User Access Token** (token ở ô trên cùng — không cần tìm token của từng Page nữa).
3. Vào tab **"🔗 Kết nối Facebook"** trong app, dán User Access Token vào, bấm
   **"Kết nối & Tải danh sách Page"** — app tự động lấy về TẤT CẢ Page bạn quản lý kèm token riêng của
   từng Page.
4. Sang tab **"📤 Đăng Facebook"**, tick chọn 1 hoặc nhiều Page muốn đăng, rồi đăng bài — app sẽ đăng
   đồng thời lên tất cả Page đã chọn và báo kết quả (thành công/thất bại) riêng cho từng Page.

Ghi chú kỹ thuật: token lấy từ Graph API Explorer thường hết hạn sau ~1-2 giờ. Nếu đã cấu hình App
ID/Secret ở bước 1, app tự động đổi sang **long-lived token** (không tự hết hạn theo lịch cố định) ngay
khi bạn bấm "Kết nối". Xem thêm: https://developers.facebook.com/docs/pages/access-tokens

### TikTok (đăng video qua Content Posting API)

Khác với Facebook, TikTok không có "playground" để tự lấy token — bạn cần tạo 1 app TikTok và đăng
nhập qua OAuth thật từ trong ứng dụng.

1. Vào https://developers.tiktok.com/apps → tạo app mới → thêm 2 sản phẩm **"Login Kit"** và
   **"Content Posting API"**.
2. Trong cấu hình Login Kit, đăng ký **Redirect URI** chính xác là:
   `http://127.0.0.1:5577/callback/` (app hiển thị sẵn giá trị này ở tab "Kết nối TikTok" để bạn copy —
   lưu ý TikTok yêu cầu đúng "127.0.0.1", không chấp nhận "localhost").
3. Lấy **Client Key** và **Client Secret** của app, dán vào tab **Cài đặt** của Claude Content Studio.
4. Sang tab **"🔗 Kết nối TikTok"**, bấm **"Đăng nhập TikTok"** — trình duyệt mặc định sẽ mở ra để bạn
   đăng nhập/đồng ý quyền, sau đó tự động quay lại ứng dụng.
5. Sang tab **"🎵 Đăng TikTok"**: chọn video (từ tab Tạo Video/Bộ sưu tập, hoặc chọn file thủ công),
   nhập caption, chọn quyền riêng tư, rồi bấm "Đăng lên TikTok".

Lưu ý quan trọng: cho đến khi app TikTok của bạn được TikTok **duyệt (audit)**, mọi video đăng qua
API chỉ hiển thị ở chế độ **riêng tư (Chỉ mình tôi)**, bất kể bạn chọn quyền riêng tư nào lúc đăng —
đây là giới hạn từ phía TikTok với app chưa qua kiểm duyệt, không phải lỗi của ứng dụng. Access token
tự hết hạn sau 24 giờ nhưng app tự làm mới bằng refresh token (hạn 365 ngày) mỗi lần đăng bài, không
cần đăng nhập lại thường xuyên. Xem thêm: https://developers.tiktok.com/doc/content-posting-api-get-started

### YouTube (đăng video qua Data API v3)

1. Vào https://console.cloud.google.com → tạo project mới (hoặc dùng project có sẵn) → vào **"APIs & Services"**
   → **"Library"** → bật **"YouTube Data API v3"**.
2. Vào **"APIs & Services → OAuth consent screen"**: chọn User Type "External", điền thông tin cơ bản,
   sang mục **"Test users"** thêm chính địa chỉ Gmail bạn sẽ dùng để đăng video.
3. Vào **"Credentials"** → **"Create Credentials"** → **"OAuth client ID"** → chọn loại **"Desktop app"**
   → lấy **Client ID** và **Client Secret** (loại Desktop app không cần khai báo Redirect URI thủ công,
   Google tự chấp nhận cổng loopback ứng dụng mở ra khi đăng nhập).
4. Dán Client ID/Client Secret vào tab **Cài đặt** của Claude Content Studio.
5. Sang tab **"🔗 Kết nối YouTube"**, bấm **"Đăng nhập Google/YouTube"** — trình duyệt mặc định mở ra để
   bạn đăng nhập/đồng ý quyền, sau đó tự động quay lại ứng dụng.
6. Sang tab **"🎥 Đăng YouTube"**: chọn video, nhập tiêu đề/mô tả/tag, chọn chuyên mục và quyền riêng tư,
   rồi bấm "Đăng lên YouTube".

Lưu ý quan trọng: khi OAuth consent screen còn ở trạng thái **"Testing"** (mặc định lúc mới tạo), phiên
đăng nhập của bạn (refresh token) chỉ dùng được **7 ngày** rồi cần đăng nhập lại. Muốn dùng lâu dài không
cần đăng nhập lại, vào Google Cloud Console chuyển **Publishing status** sang **"In production"** — lúc
đó Google sẽ hiện cảnh báo "ứng dụng chưa được xác minh" khi đăng nhập, bấm **Advanced → Go to (tên app)**
để tiếp tục vì đây chính là app bạn tự tạo, an toàn để bỏ qua cảnh báo này. Google giới hạn khoảng 100
lượt tải video lên/ngày cho project dùng quota mặc định (đủ dùng cho đăng cá nhân/doanh nghiệp nhỏ); cần
nhiều hơn thì xin tăng quota trong Google Cloud Console. Xem thêm:
https://developers.google.com/youtube/v3/guides/uploading_a_video

### MongoDB Atlas (tuỳ chọn — lưu lịch sử content/ảnh/video/bài đăng trên cloud)

Mặc định app lưu lịch sử vào 1 file SQLite ngay trên máy. Nếu muốn lưu trên MongoDB Atlas (xem được
từ nhiều máy, không mất khi cài lại máy), làm theo các bước sau — **không bắt buộc**, bỏ qua phần này
nếu dùng SQLite cục bộ là đủ:

1. Tạo tài khoản & cluster miễn phí tại https://www.mongodb.com/cloud/atlas/register (chọn gói M0 Free).
2. Trong Atlas → **Database Access**: tạo 1 user (username/password) — dùng để đăng nhập, không phải
   tài khoản Atlas của bạn.
3. Trong Atlas → **Network Access**: thêm địa chỉ IP của máy bạn (hoặc `0.0.0.0/0` để cho phép mọi IP —
   chỉ nên dùng khi test, vì cho phép kết nối từ bất kỳ đâu miễn có đúng username/password).
4. Bấm **Connect** trên cluster → **Drivers** → copy chuỗi kết nối dạng:
   `mongodb+srv://<username>:<password>@cluster0.xxxxx.mongodb.net/`
   Thay `<username>`/`<password>` bằng user đã tạo ở bước 2.
5. Vào **Cài đặt** trong app, dán chuỗi này vào **"MongoDB Atlas connection string"**, đặt tên database
   nếu muốn (mặc định `claude_content_studio`), bấm **"Kiểm tra"** để xác nhận kết nối được, rồi **Lưu**.

Từ lúc này, mọi content/ảnh/video/bài đăng mới sẽ tự động ghi vào MongoDB Atlas thay vì SQLite. Xoá
connection string (để trống) và Lưu lại để quay về lưu cục bộ. API key (Anthropic/OpenAI/HeyGen/Facebook)
**không** lưu vào MongoDB — vẫn nằm trong Windows Credential Manager như trước.

## 3. Chạy app

```bash
python run.py
```

## 4. Luồng sử dụng

1. **Viết Content**: chọn nhà cung cấp (Claude hoặc OpenAI) → nhập chủ đề → AI viết bài → chỉnh sửa nếu cần.
   Nhà cung cấp vừa chọn cũng sẽ được dùng cho các nút "Gợi ý" ở tab Ảnh/Video.
2. Bấm "→ Dùng cho tab Ảnh/Video/Đăng Facebook" để chuyển nội dung sang các bước sau.
3. **Tạo Ảnh**: bấm "Gợi ý prompt từ content" (tuỳ chọn) → Tạo ảnh.
4. **Tạo Video**: tải danh sách Avatar/Voice → gợi ý kịch bản (tuỳ chọn) → Tạo video (mất vài phút).
5. **Kết nối Facebook** (chỉ cần làm 1 lần): kết nối để lấy danh sách Page — xem phần "Facebook — kết nối nhiều Page" ở trên.
6. **Đăng Facebook**: tick chọn 1 hoặc nhiều Page → kiểm tra nội dung/ảnh/video đính kèm → chọn "Đăng ngay" hoặc
   "Lên lịch" → Đăng bài. Kết quả từng Page (thành công/thất bại) hiển thị riêng biệt.
7. **Kết nối & Đăng TikTok** (tuỳ chọn, chỉ hỗ trợ video): kết nối 1 lần ở tab "Kết nối TikTok" — xem phần
   "TikTok" ở trên — rồi sang tab "Đăng TikTok" để đăng video vừa tạo.
8. **Kết nối & Đăng YouTube** (tuỳ chọn, chỉ hỗ trợ video): kết nối 1 lần ở tab "Kết nối YouTube" — xem phần
   "YouTube" ở trên — rồi sang tab "Đăng YouTube" để tải video vừa tạo lên kênh của bạn.

## 5. Quy trình tự động ("🚀 Tự động hoá", nằm dưới mục Cài đặt)

Màn hình này gộp toàn bộ luồng thủ công ở trên thành 1 bước: bạn chỉ cần nhập **1 ý tưởng**,
app sẽ tự động viết content → tạo ảnh (OpenAI) hoặc video (HeyGen) tuỳ bạn chọn → rồi bạn xem lại
và bấm **Đăng bài** để đăng lên các Page đã chọn.

1. Nhập ý tưởng, chọn nhà cung cấp viết content, giọng điệu.
2. Chọn **"Đính kèm khi đăng"**: Không đính kèm / Ảnh / Video (Facebook chỉ cho đính 1 loại/bài,
   nên app chỉ tạo đúng loại bạn chọn để đỡ tốn API). Nếu chọn Video, cần bấm "Tải danh sách Avatar/Voice"
   và chọn 1 lần đầu — lần sau app tự nhớ lựa chọn này.
3. Bấm **"🚀 Chạy quy trình tự động"** — app tự chạy toàn bộ các bước phía trên, không cần thao tác gì thêm.
4. Khi xong, xem lại nội dung/ảnh/video ở phần dưới (có thể sửa lại content nếu muốn), chọn Page, rồi bấm
   **Đăng bài**. Bước xác nhận cuối này được giữ lại có chủ đích — để bạn luôn nhìn thấy nội dung thật
   trước khi nó lên Facebook công khai, tránh trường hợp AI viết sai mà không ai kiểm tra trước khi đăng.

## Ghi chú bảo mật

- Toàn bộ API key/token — kể cả token riêng của từng Facebook Page và access/refresh token
  TikTok/YouTube — được lưu trong **Windows Credential Manager** qua thư viện `keyring`, không lưu
  dạng văn bản thuần trong file cấu hình.
- App chỉ đăng bài khi bạn chủ động bấm nút "Đăng bài"/"Đăng lên TikTok"/"Đăng lên YouTube" và xác
  nhận — không có gì tự động đăng lên Facebook, TikTok hay YouTube.
- Chi phí API (Anthropic/OpenAI/HeyGen/Grok) phát sinh theo mức sử dụng thực tế của bạn với từng nhà
  cung cấp. TikTok Content Posting API và YouTube Data API v3 hiện miễn phí (YouTube có giới hạn quota
  số lượt tải video lên/ngày, xem phần "YouTube" ở trên).

## Giới hạn phiên bản hiện tại

- Không tự động hoá đăng nhập Facebook bằng trình duyệt (OAuth redirect) trong app — bạn tự lấy
  User Access Token từ Graph API Explorer rồi dán vào tab "Kết nối Facebook".
- Chưa đóng gói thành file `.exe` — chạy trực tiếp bằng `python run.py` (có thể dùng PyInstaller sau nếu cần).
- Mỗi lần đăng chỉ hỗ trợ 1 nội dung (text, hoặc kèm 1 ảnh, hoặc kèm 1 video) và tối đa 1 lịch đăng/lần,
  nhưng có thể đăng nội dung đó lên nhiều Page cùng lúc.
- TikTok và YouTube: chỉ hỗ trợ đăng **video** (không hỗ trợ ảnh/carousel), chỉ kết nối được **1 tài
  khoản/kênh** mỗi loại (không hỗ trợ nhiều tài khoản như Facebook), và không hỗ trợ lên lịch đăng —
  đăng là lên ngay lập tức.


mongodb://it_admin:BrPN34xFmHo5U4Nr@ac-ixgqgwe-shard-00-00.dtz81lj.mongodb.net:27017,ac-ixgqgwe-shard-00-01.dtz81lj.mongodb.net:27017,ac-ixgqgwe-shard-00-02.dtz81lj.mongodb.net:27017/claude_content_studio?ssl=true&replicaSet=atlas-rqggr5-shard-0&authSource=admin&appName=Cluster0



Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.venv\Scripts\activate