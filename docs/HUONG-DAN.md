# POD Trend Radar — Hướng dẫn sử dụng

Cập nhật: 09/10/2026

POD Trend Radar tìm ngách áo (t-shirt, sweatshirt, hoodie) đang lên ở thị trường Mỹ, mẫu Etsy đang bứt phá và shop đang ra đơn, rồi báo về Telegram. App chạy trên máy Mac, tự quét 2 lần/ngày lúc **8:00** và **20:00**.

**Nguồn dữ liệu** (chỉ thị trường Mỹ):

- **Etsy** (API chính thức): listing áo bán chạy theo từng keyword trong Watchlist, listing mới đăng để tìm mẫu bứt phá, thông tin shop (tổng đơn đã bán, số listing, rating).
- **Google gợi ý tìm kiếm**: cụm người Mỹ hay gõ sau "<keyword> shirt / hoodie / sweatshirt" → ngách con.
- **Google xu hướng ngày**: chủ đề đang nổi trong ngày ở Mỹ.

Amazon đã gỡ khỏi app (09/10/2026). Sau mỗi lần quét: chấm điểm ngách → tìm tin đáng báo → gửi 1 thông báo Telegram → sao lưu database.

---

## 1. Cách chạy

Thường ngày **không cần gõ lệnh**: app tự bật khi đăng nhập Mac và tự quét lúc 8:00/20:00. Các lệnh dưới đây chạy trong thư mục dự án `research-idea`.

| Việc | Lệnh / địa chỉ |
| --- | --- |
| Mở app trên Mac | http://localhost:3737 |
| Mở từ điện thoại / máy khác (bật Tailscale) | http://phuongbd.tail3efd85.ts.net:3737 |
| Bật app (backend + giao diện) | `make up` |
| Tắt app | `make down` |
| Khởi động lại | `make down && make up` |
| Quét ngay, không chờ 8:00/20:00 | `make scan-now` (~8–12 phút, có thể gửi tin Telegram) |
| Trạng thái lịch quét + log gần nhất | `make daily-status` |
| Sao lưu database ngay | `make backup` |
| Xem trước tin tổng kết tuần (gửi thật vào Telegram) | `make digest-now` |

**Cổng**

- **3737** — giao diện, mở được từ máy khác qua Tailscale.
- **8020** — backend API, chỉ nghe trong Mac; giao diện tự chuyển `/api` sang đây.
- Trùng cổng với app khác: `make down && make up UI_PORT=4000` hoặc `API_PORT=8030`.

**Tự động trên Mac** (đã cài sẵn)

- Tự bật khi đăng nhập: `make install-autostart` / `make uninstall-autostart`.
- Quét 8:00 và 20:00: `make install-daily` (đổi giờ: `make install-daily DAILY_HOURS="7 19"`). Máy ngủ đúng giờ → quét bù khi máy thức.
- Sao lưu: sau mỗi lần quét, 1 bản/ngày trong `backend/data/backups/`, giữ 14 bản.

Mac phải bật và không ngủ thì điện thoại mới vào được app. Khi cắm sạc: System Settings → Battery → bật "Prevent automatic sleeping when the display is off".

---

## 2. Các menu

### Trend Radar — "Ngách đang lên" (`/`)

Danh sách ngách xếp theo **điểm 0–100** cho thị trường Mỹ.

- **Điểm** = nhu cầu (lượt xem Etsy, gợi ý Google…) + đà tăng (so với tuần trước) − cạnh tranh (số listing trên Etsy). Thước chấm halftone cạnh điểm.
- **Tăng trưởng** ▲▼: so với 7–30 ngày trước (cần vài tuần dữ liệu mới có).
- **Nguồn**: chấm màu cho biết ngách có từ đâu (cyan = Etsy, vàng = Google).
- Khối **Sắp tới**: các dịp lễ gần nhất từ Lịch mùa vụ.
- Bộ lọc: **Nguồn**, **Loại keyword** (Seed + khám phá / Chỉ seed / Chỉ ngách khám phá), **Chỉ POD** (ẩn cụm không phải nhu cầu mua áo).
- **Cạnh tranh**: tổng số listing Etsy cho "<ngách> shirt" — Thấp (< 10.000), Vừa (< 50.000), Cao. Có cho keyword Watchlist và khoảng 30 ngách con điểm cao nhất (cập nhật mỗi 3 ngày).
- Sắp xếp **Cơ hội** = độ hot (nhu cầu + đà tăng) × độ ít cạnh tranh — ngách đang lên mà ít đối thủ lên đầu.
- Bấm tên ngách → **trang chi tiết**: 5 chỉ số, biểu đồ theo nguồn, keyword liên quan (ngách con/cha), sản phẩm Etsy.
- Nút **Theo dõi** → đưa ngách vào Watchlist. Link **Phân tích** → trang Phân tích ngách.

### Phân tích ngách (`/niche`)

Nhập một keyword (hoặc bấm chip Watchlist) để xem trong một trang:

- **Cạnh tranh**: tổng listing Etsy theo áo thun / sweatshirt / hoodie và mức Thấp/Vừa/Cao.
- **Giá tham khảo**: giá thấp (p25) / trung vị / cao (p75) theo loại áo của listing shop Mỹ trong ngách, và giá trung vị của hàng bứt phá — dùng để đặt giá TikTok Shop.
- **Top Tags**: tag các listing trong ngách dùng nhiều nhất, số listing bứt phá dùng tag, nhãn **🔥 nổi** khi tag xuất hiện ở hàng bứt phá nhiều hơn bình thường. Lọc theo loại áo.
- **Bộ 13 tag**: 13 tag tốt nhất (≤ 20 ký tự, bỏ trùng số ít/số nhiều, ưu tiên tag của hàng bứt phá). Nút **Copy tag** (`a, b, c`) và **Copy #hashtag** (cho TikTok).
- **Cụm từ cho tiêu đề**: các cụm nhiều từ nên có trong tiêu đề sản phẩm.
- "Hàng bứt phá" ở đây gồm Super Breakout, Steady Grower và Graduated.

### Việc của tôi (`/work`)

Đánh dấu ngách hoặc listing bằng nút trạng thái (có ở Trend Radar, Watchlist, Etsy bứt phá, Bán chạy, Phân tích ngách): **💡 Ý tưởng → 🎨 Đang thiết kế → ✅ Đã đăng**, hoặc **⏸ Bỏ qua**, kèm ghi chú. Trang này gom tất cả theo trạng thái.

- Ngách/listing **Đã đăng** hoặc **Bỏ qua** sẽ **không có tin mới / Telegram** nữa.

### Watchlist — "Ngách đang theo dõi" (`/watchlist`)

Các keyword bạn theo dõi (hiện: football mom, game day, pickleball, hockey mom, basketball mom, fantasy football). Etsy, Google gợi ý và Etsy bứt phá dùng danh sách này để quét.

- Ô **Keyword mới** → Theo dõi. Mỗi keyword tốn thêm vài request Etsy/lần quét.
- Mỗi thẻ keyword: điểm, **ngách con** (bấm được), số mẫu **Super Breakout / Steady Grower** kèm ảnh, nút **Xem chi tiết**, **Xem listing** (mở Etsy bứt phá lọc sẵn), **Bỏ theo dõi**, số tin trong 7 ngày.
- Mục **Shop đang theo dõi**: các shop bạn ☆ ở trang Shop — +đơn 7/30 ngày, tổng đơn, +yêu thích 7 ngày.
- Keyword khớp **nguyên từ**: `nurse` không khớp "nursery"; số nhiều vẫn khớp ("football moms").

### Listing Signals — "Etsy bứt phá" (`/signals`)

Mẫu áo **mới đăng (≤ 30 ngày)** của shop Mỹ đang tăng lượt xem/lượt lưu nhanh, theo dõi mỗi ngày đến 45 ngày tuổi.

| Trạng thái | Ý nghĩa |
| --- | --- |
| Super Breakout | ≤ 14 ngày tuổi, ≥ 5 lượt lưu/ngày, DSR ≥ 15% |
| Steady Grower | ≥ 2 lượt lưu/ngày, DSR ≥ 5% |
| Graduated | ≥ 30 ngày tuổi, ≥ 30 lượt lưu, vẫn tăng |
| Calibrating | mới phát hiện, cần ≥ 2 lần quét để tính mức tăng |

- **DSR** = lượt lưu mới ÷ lượt xem mới (tỉ lệ người xem lưu lại).
- Lọc theo **Keyword** (Watchlist), tuổi listing; sắp xếp theo Δ lượt lưu, DSR, Δ lượt xem, mới nhất.
- Listing bán **file thiết kế** (PNG/SVG, mockup, digital download, DTF transfer) bị loại.
- Bấm ảnh để phóng to; tag dưới thẻ dẫn sang Trend Radar.

### Shop — "Shop đang ra đơn" (`/shops`)

Shop Etsy ở Mỹ app thấy qua các lần quét. App chụp **tổng đơn đã bán** của shop mỗi ngày.

- **+Đơn 7 / 30 ngày** = tổng đơn hôm nay − tổng đơn 7/30 ngày trước. Chưa đủ ngày → kèm "(n ngày)"; chưa đủ dữ liệu → "—".
- **Đơn/listing** = tổng đơn ÷ số listing đang bán (shop ít listing bán nhiều = mẫu mạnh).
- Tìm theo ngách (ví dụ `game day`), lọc tổng đơn, số listing, đơn/listing, năm mở shop, rating; lọc nhanh: Đang lên 7 ngày, Shop mới 2025–2026, Ít listing bán nhiều, Shop lớn.
- **☆** → theo dõi shop (hiện ở Watchlist, cập nhật mỗi lần quét, có tin 🏪).
- Bấm tên shop → biểu đồ tổng đơn theo ngày + sản phẩm của shop.
- Bắt đầu thu thập từ 09/10/2026; số **+đơn 7 ngày** đủ chuẩn từ khoảng 16/10/2026.

### Bán chạy — "Best Sellers" (`/products`)

Sản phẩm Etsy bán chạy theo từng keyword trong Watchlist, xếp theo mức tăng gần đây (reviews/lượt lưu/lượt xem mỗi tuần).

- Nhãn **🔥 Hot**: top 10% tăng nhanh nhất trong nhóm cùng loại áo.
- Lọc theo keyword, loại áo; ẩn sản phẩm có thể có bản quyền (viền đỏ tía "đừng sao chép").
- Velocity/🔥 cần ≥ 2 lần quét cách nhau ≥ 3 ngày.

### Tin mới (`/alerts`)

Các phát hiện sau mỗi lần quét. Số trên menu = số tin chưa đọc; mở trang là đánh dấu đã đọc.

| Tin | Khi nào | Chuông Telegram |
| --- | --- | --- |
| 🚀 Ngách bứt phá | ngách trong Watchlist (hoặc ngách con) điểm ≥ 60 và tăng > 20% | có |
| 🔥 Etsy bứt phá | listing thành Super Breakout (mọi ngách) | có |
| 🔥 Etsy bứt phá | listing thành Steady Grower (ngách trong Watchlist) | im lặng |
| ⭐ Sản phẩm hot | sản phẩm của keyword Watchlist vừa có nhãn 🔥 | im lặng |
| 🏪 Shop tăng tốc | shop đang theo dõi bán ≥ 30 đơn/7 ngày và ≥ 1,5× tuần trước | im lặng |

**Telegram — chống spam**

- Mỗi lần quét **1 thông báo** (album tối đa 5 ảnh, danh sách trong chú thích, "… và N tin khác").
- **Giờ yên lặng 22:00–7:00**: tin giữ lại, gửi ở lần quét sáng.
- Mỗi ngách/sản phẩm/shop chỉ báo 1 lần trong 7 ngày, trừ khi lên mức cao hơn.
- **Tổng kết tuần**: sáng thứ Hai (lần quét đầu tuần) — ngách tăng mạnh 7 ngày, Watchlist, top shop, dịp sắp tới, số tin tuần qua.
- Nút **Gửi tin thử** trên trang để kiểm tra kết nối. Cài lại bot: `make telegram-setup`.
- Ngưỡng chỉnh trong `backend/config/alerts.yaml`.

### Lịch mùa vụ (`/calendar`)

Các dịp bán hàng ở Mỹ (Halloween, Black Friday–Cyber Monday, 11.11, 12.12, Christmas, Valentine, Mother's Day…) với mốc cần làm, tính ngược từ ngày lễ với 10 ngày fulfillment POD:

- Giai đoạn: **Sắp tới → 🎨 Thiết kế → 🚀 Lên sản phẩm → 📈 Đẩy mạnh → ⏰ Quá hạn đặt hàng → 🔥 Cao điểm → Hết mùa**; giai đoạn hiện tại hiện bằng nhãn kèm lời khuyên. Hạn đặt hàng = ngày lễ − 10 ngày fulfillment − 3 ngày dự phòng.
- **Ý tưởng ghép ngách**: dịp × keyword Watchlist (ví dụ "halloween football mom"); bấm **Theo dõi** để đưa vào Watchlist.
- Chỉnh danh sách dịp và số ngày fulfillment trong `backend/config/us_calendar.yaml`.

### Cài đặt (`/settings`)

- **Watchlist keyword**: danh sách hiện tại, bấm để mở trang chi tiết, xóa keyword (thêm keyword ở trang Watchlist).
- **Nguồn dữ liệu**: bật/tắt từng nguồn (Etsy, Google gợi ý, Google xu hướng ngày, Etsy bứt phá, Etsy đếm cạnh tranh), trạng thái lần quét gần nhất. Nút **Quét ngay**.
- **Lịch sử quét**: từng lần quét, nguồn, số bản ghi, lỗi (nếu có).

Khối **"Bản in hôm nay"** cuối thanh menu trái cho biết từng nguồn quét lần cuối khi nào và có lỗi không.

---

## 3. Cấu hình và xử lý sự cố

| File | Chỉnh gì |
| --- | --- |
| `backend/.env` | Etsy API key, Telegram token/chat, địa chỉ app, thư mục sao lưu (không chia sẻ file này) |
| `backend/config/alerts.yaml` | Ngưỡng tin, số tin mỗi thông báo, giờ yên lặng |
| `backend/config/listing_signals.yaml` | Truy vấn Etsy bứt phá, ngưỡng Super Breakout / Steady Grower |
| `backend/config/us_calendar.yaml` | Dịp lễ, ngày fulfillment |
| `backend/config/pod_filter.yaml` | Từ loại khỏi Trend Radar |

| Vấn đề | Cách xử lý |
| --- | --- |
| Không mở được localhost:3737 | `make up`; xem `backend/data/logs/frontend.log` và `backend.log` |
| Điện thoại không vào được | Mac đang bật? Tailscale bật trên cả hai máy, cùng tài khoản? |
| Trang báo "Không tải được dữ liệu" | Backend tắt: `make down && make up` |
| Không thấy tin Telegram | Tin im lặng không hiện thông báo → mở chat với bot; kiểm tra bằng nút **Gửi tin thử** ở Tin mới |
| Lần quét lỗi | `make daily-status`; xem `backend/data/logs/daily-scan.log` |
| Cần khôi phục dữ liệu | `make down`, chép một bản trong `backend/data/backups/` đè lên `backend/data/radar.db`, `make up` |
