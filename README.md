# Claude Content Studio

Desktop app (Python + PySide6) dùng **Claude API làm lõi** để viết content, sinh ảnh (OpenAI),
sinh video avatar (HeyGen), rồi đăng thẳng lên Facebook Page (Graph API).

### Thu gọn tiến trình

Trong hộp thoại loading, bấm **Thu gọn**, **X** hoặc **Esc** để ẩn hộp thoại;
tác vụ tiếp tục chạy. Biểu tượng đồng hồ cạnh nút tài khoản hiển thị số tác vụ.
Bấm biểu tượng để mở lại; nếu có nhiều tác vụ, chọn tác vụ trong danh sách.
Kết quả hoàn tất, dừng hoặc lỗi được giữ để xem lại; đóng sau khi xem kết quả
sẽ bỏ mục đó khỏi biểu tượng. Mỗi chức năng giữ tiến trình gần nhất trong phiên mở ứng dụng.

### Theo dõi chi phí

Dashboard hiển thị **Chi phí đã sử dụng · ước tính (USD)** và chi phí theo từng model,
tính từ token đã ghi nhận ở SQLite hoặc MongoDB. Bấm **Làm mới** để cập nhật.
Bảng giá chuẩn được đối chiếu ngày 23/09/2026 từ
[OpenAI](https://developers.openai.com/api/docs/pricing) và
[Claude](https://platform.claude.com/docs/en/about-claude/pricing).
Dữ liệu ảnh cũ chưa tách token văn bản/ảnh đầu vào nên hiển thị khoảng tiền.
Model chưa có giá hoặc thiếu token hiển thị **Chưa đủ dữ liệu**, không được tính là miễn phí.
Đây là ước tính theo bảng giá trên, không phải hóa đơn hoặc số dư tài khoản;
chưa điều chỉnh cache, thuế, tín dụng, phí video/âm thanh và yêu cầu ngoài lịch sử.

### Tạo video Grok theo từng bước

Trong tab **Video**, chọn **Grok**. Phần chuẩn bị được tách thành hai màn hình ngắn
trước khi dựng video: **Vật liệu → Kịch bản → Tạo video**.

1. **Vật liệu:** ghi bối cảnh, chọn khung hình và tạo ảnh với OpenAI hoặc chọn ảnh có sẵn.
   Bước này chưa cần kịch bản.
   Có thể **Đính kèm hình mẫu để tạo ảnh**, nhập bối cảnh/mô tả rồi tạo vật liệu dựa trên mẫu.
   Hỗ trợ một hình mẫu PNG/JPG/WebP nhỏ hơn 50 MB; có nút **Xem**, **Đổi hình mẫu** và **Bỏ mẫu**.
   Chọn model GPT Image trong Cài đặt để dùng tính năng này. Hình mẫu là đầu vào tạo ảnh;
   ảnh kết quả mới được tự động đính kèm vào luồng dựng video.
   Mục **Đính kèm khuôn mặt tham chiếu** nhận một ảnh chân dung riêng, có thể dùng cùng
   hình mẫu bối cảnh. Có nút xem, đổi và bỏ ảnh khuôn mặt. Khi tạo vật liệu, ứng dụng gửi
   cả hai ảnh và yêu cầu ưu tiên đặc điểm khuôn mặt từ ảnh chân dung cho nhân vật chính.
   Mục **Tùy chỉnh mô tả và loại ảnh** cho phép mô tả riêng hoặc tạo ảnh tham chiếu
   (tối đa 4 ảnh). Ảnh tự động đính kèm và hiển thị lớn bên phải; chọn từng ảnh để xem lại.
   Có ít nhất một ảnh thì mới tiếp tục. Tạo lại ảnh khởi đầu sẽ thay ảnh đang chọn;
   ảnh đã tạo được lưu trong thư mục đầu ra và lịch sử hình ảnh.
   Để sửa ảnh, chọn vật liệu bên phải rồi nhập yêu cầu vào **Chỉnh ảnh đang chọn bằng mô tả**
   và bấm **Áp dụng chỉnh sửa** (ví dụ: đổi nền, thêm đạo cụ, đổi trang phục).
   Mỗi lần sửa dùng chính ảnh đang chọn và ảnh khuôn mặt tham chiếu nếu có. Kết quả thay
   đúng vật liệu đó để dùng cho video; ảnh gốc vẫn được giữ. Có thể sửa tiếp hoặc chọn lại
   **Phiên bản** trước trong phiên làm việc. Mọi ảnh chỉnh sửa được lưu vào lịch sử hình ảnh.
   Nút **Mở trình chỉnh sửa ảnh · Chọn vùng** mở không gian chỉnh sửa lớn với lịch sử ảnh
   thu nhỏ, thu phóng, di chuyển ảnh, khoanh nhiều vùng bằng chuột và đặt tên từng vùng.
   Tích các vùng cần sửa, nhập mô tả rồi bấm **Áp dụng chỉnh sửa AI**; bỏ mọi vùng để sửa
   toàn ảnh. Có thể cắt ảnh theo vùng, lưu ảnh ra tệp và chọn **Dùng ảnh này làm vật liệu**.
   Bấm **AI phân tích lớp** để nhận diện các vật liệu (tóc, áo, quần, giày, nền…)
   và tinh chỉnh đường biên theo điểm ảnh. Chọn lớp trong danh sách hoặc bấm trực tiếp
   lên ảnh; **Ctrl + bấm** để chọn nhiều lớp. Mỗi lớp có ảnh thu nhỏ, tên, mô tả vị trí
   và tọa độ trên ảnh gốc; các thông tin này được gửi cùng yêu cầu chỉnh sửa.
   Dùng **Tô thêm vào lớp / Xóa bớt khỏi lớp** để sửa biên, hoặc khoanh vùng thủ công.
   **Lưu lớp thành vật liệu PNG** xuất riêng lớp với nền trong suốt vào tệp và lịch sử.
   Phân tích lớp dùng model riêng ở mục **Model phân tích lớp**
   trong trình chỉnh sửa: mặc định **GPT-5.4**, hoặc **GPT-4o mini** để tiết kiệm.
   Lựa chọn được lưu khi bấm phân tích, không đổi model viết content. GPT-5.4 dùng
   ảnh chi tiết `original` (cạnh dài tối đa 3072 px) và suy luận cao; có thể chậm
   và tốn phí hơn. Token và chi phí ước tính được ghi trên Dashboard.
   Có thể chọn **Grok 4.7 · xAI**, dùng **Grok API key** đã nhập trong Cài đặt;
   các model GPT dùng OpenAI API key. Grok nhận diện lớp qua API thị giác rồi ứng dụng
   tinh chỉnh vùng chọn; chưa bảo đảm giống bộ tách lớp trên grok.com.
   Chỉnh sửa ảnh bằng mô tả sau khi chọn lớp vẫn dùng OpenAI như trước.
   Tính năng cần numpy/OpenCV trong requirements.txt. Nếu tài khoản chưa có quyền
   dùng model, lỗi được hiển thị và giữ nguyên các lớp cũ; không tự đổi sang model khác.
   Đường biên AI chỉ là ước lượng, cần xem lại trước khi áp dụng. Với chỉnh sửa theo vùng,
   ứng dụng ghép kết quả vào vùng chọn và giữ nguyên điểm ảnh bên ngoài.
   Phân tích hỗ trợ vùng rỗng bên trong lớp, loại vật thể khỏi lớp nền và xử lý vùng
   chồng lấn để mỗi điểm ảnh chỉ thuộc một lớp trong kết quả phân tích. Lớp chưa tinh
   chỉnh được biên hoặc có chồng lấn lớn sẽ được báo cần kiểm tra. Bấm vào chỗ trống
   sẽ bỏ vùng chọn cũ; cần chọn lại lớp trước khi chỉnh sửa.
   Đây là nhận diện bằng mô hình thị giác kết hợp GrabCut, chưa phải bộ phân vùng
   chuyên dụng; ảnh có nhiều chi tiết hoặc màu tương tự nhau vẫn có thể cần sửa bằng cọ.
   Các lớp được giữ theo từng phiên bản trong lúc cửa sổ chỉnh sửa còn mở;
   ảnh phiên bản mới cần phân tích lại để khớp vị trí đồ vật.
   Trình chỉnh sửa cũng có trong tab **Hình ảnh**, hỗ trợ mở ảnh từ máy.
2. **Kịch bản:** dựa trên ảnh và bối cảnh đã chuẩn bị để viết nội dung, hành động, lời thoại
   và chuyển động máy quay. Mở **Lấy ý tưởng từ video mẫu** nếu cần phân tích mẫu.
   Có kịch bản thì nút **Tiếp tục** mới mở; ảnh từ bước 1 vẫn hiển thị bên phải để tham khảo.
3. **Tạo video:** kiểm tra kịch bản, bối cảnh, danh sách ảnh, độ phân giải và thời lượng,
   rồi bấm **Tạo video với Grok**. Ứng dụng gửi đầy đủ nội dung và ảnh đã đính kèm.
   Khi hoàn tất, bấm **Mở video** hoặc chuyển video sang tab đăng bài.

Mỗi màn hình chỉ hiển thị nội dung của bước hiện tại. Các nút **Quay lại** giữ nguyên
kịch bản và vật liệu; trong lúc xử lý, việc chuyển bước và sửa đầu vào được khóa.

Luồng Grok yêu cầu kịch bản và ít nhất một ảnh hợp lệ. Tạo ảnh cần OpenAI API key;
tạo video cần Grok API key. Nếu đã có ảnh, có thể đính kèm mà không gọi OpenAI.
HeyGen vẫn dùng kịch bản, avatar và voice như trước.

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

## Kho bài viết đã đăng

- Sau khi quy trình tự động đăng thành công, ứng dụng lưu nội dung, mã bài, nơi đăng và bản sao riêng của tất cả ảnh/video đính kèm vào kho. Mỗi nơi đăng có một bản ghi; nơi đăng thất bại không xuất hiện trong danh sách thành công.
- Chọn **Kho bài viết đã đăng** trên thanh điều hướng, bấm một bài để mở dialog xem trước điện thoại. Chọn từng ảnh để xem đủ album; video có nút phát/tạm dừng và mở bằng ứng dụng trên máy.
- **Lưu bản chỉnh sửa** giữ bản nháp qua lần khởi động sau, chưa thay đổi bài trên nền tảng. **Đăng lại thành bài mới** dùng nội dung đang sửa cùng toàn bộ tệp trong kho. Facebook đăng vào Page gốc; TikTok/YouTube dùng tài khoản đang kết nối và quyền riêng tư trong cài đặt, hiển thị trước khi xác nhận.
- **Cập nhật nội dung bài gốc** sửa chữ/mô tả trên Facebook hoặc YouTube, giữ nguyên ảnh/video. YouTube giữ tiêu đề, tag và quyền riêng tư; có thể cần kết nối lại để cấp quyền sửa video theo [YouTube videos.update](https://developers.google.com/youtube/v3/docs/videos/update). TikTok hiện chỉ hỗ trợ đăng lại trong ứng dụng này.
- Tệp nằm trong thư mục dữ liệu ứng dụng `published_posts`, kèm `post.json` lưu thông tin gốc. MongoDB lưu bản ghi, còn tệp vẫn nằm trên máy hiện tại. Khi chuyển máy cần sao lưu cả thư mục này. Bài cũ vẫn đọc được nhưng các đường dẫn trước khi có tính năng này không tự khôi phục tệp đã mất.
- Nếu đã đăng thành công nhưng sao chép tệp/lưu kho gặp lỗi, ứng dụng báo rõ và không tự đăng lại bài đó. Bài lên lịch được ghi rõ thời gian, không coi là đã phát hành ngay.

## Quản lý lịch đăng Facebook

Mở **Quản lý → Lịch đăng Facebook** hoặc nút **Quản lý lịch đăng Facebook** trong màn hình Đăng Facebook.
Danh sách gồm các lịch đã tạo bằng ứng dụng (cả đăng thủ công và quy trình tự động), nội dung, Page,
giờ hẹn theo múi giờ máy và trạng thái. Chọn bài để đọc đầy đủ, xem ảnh/video hoặc mở trên Facebook.

- **Chờ đăng — chưa xác minh**: Facebook đã nhận yêu cầu lên lịch, chưa lấy trạng thái mới.
- **Chờ đăng**: lần kiểm tra gần nhất xác nhận chưa xuất bản và chưa tới giờ hẹn.
- **Đã đến giờ — cần kiểm tra / chưa đăng**: đã tới giờ; cần xác minh hoặc Facebook vẫn báo chưa xuất bản.
- **Đã đăng**: Facebook xác nhận đã xuất bản; màn hình ghi thời điểm xác minh gần nhất.
- **Lên lịch thất bại**: yêu cầu tạo lịch bị từ chối, kèm lý do nếu có.

Dùng **Kiểm tra bài đang chọn** hoặc **Cập nhật trạng thái trang này** để đọc trạng thái từ Facebook.
Ô hẹn giờ Facebook cũng được áp dụng khi quy trình tự động đăng sau lúc tạo nội dung; nếu giờ hẹn
không còn cách thời điểm gửi ít nhất 10 phút, ứng dụng dừng và yêu cầu chọn giờ mới. TikTok/YouTube
vẫn đăng ngay theo cấu hình. Link đính kèm được giữ trong kho khi đăng lại bài Facebook.
Nếu kết nối bị ngắt hoặc Facebook không trả mã bài, trạng thái là **Chưa xác nhận — kiểm tra Page**;
quy trình tự động tạm bỏ qua đích đó khi thử lại để tránh đăng trùng.
Kết quả được lưu lại; lỗi mạng/token/quyền truy cập được báo riêng và không bị coi là thất bại xuất bản.
Màn hình không tự suy ra “Đã đăng” chỉ vì đã qua giờ hẹn, không tự đăng lại, và không nhập các lịch
tạo ngoài ứng dụng. Các trường trạng thái dựa trên SDK chính thức của Meta:
[Post](https://github.com/facebook/facebook-python-business-sdk/blob/main/facebook_business/adobjects/post.py),
[Video](https://github.com/facebook/facebook-python-business-sdk/blob/main/facebook_business/adobjects/advideo.py).
Client Facebook sử dụng Graph API v26.0, khớp [cấu hình SDK chính thức](https://github.com/facebook/facebook-python-business-sdk/blob/main/facebook_business/apiconfig.py).

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
