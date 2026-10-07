# POD Trend Radar

Ứng dụng nghiên cứu ngách & sản phẩm POD (t-shirt, sweatshirt, hoodie) bán chạy tại Mỹ.
Phase 1: connector Etsy, theo dõi Best Sellers (snapshot hằng ngày, tăng trưởng 7 ngày, 🔥), trang Cài đặt.
Phase 2: Trend Radar — gom tín hiệu từ Etsy + Google (thị trường Mỹ), chấm điểm cơ hội 0–100 cho từng keyword/ngách.

## Cài đặt

Yêu cầu: [uv](https://docs.astral.sh/uv/) (tự tải Python 3.12), Node 20+.

```bash
make install
cp backend/.env.example backend/.env       # điền ETSY_API_KEY
cp frontend/.env.local.example frontend/.env.local
make migrate
```

### Lấy Etsy API key
1. Đăng nhập https://www.etsy.com/developers/your-apps → **Create a new app**.
2. Copy key vào `ETSY_API_KEY` trong `backend/.env` theo đúng định dạng Etsy hướng dẫn ở trang app
   (nếu Etsy yêu cầu dạng `keystring:shared_secret` thì nhập cả hai).
3. Kiểm tra: `make smoke` → phải thấy `[ok] etsy: ... products`.

## Chạy

```bash
make up     # bật backend + giao diện và mở http://localhost:3737
make down   # tắt
```

`make up` chạy bản build của giao diện (tự build lại khi code thay đổi). Giao diện tự chuyển `/api/*` sang backend, nên chỉ cần mở cổng 3737; backend chỉ nghe trong máy (127.0.0.1:8000).

(Chạy riêng từng phần khi phát triển: `make dev-backend` — API ở http://localhost:8000, tài liệu API ở /docs; `make dev-frontend`.)

Tự bật giao diện mỗi khi đăng nhập máy (sau khi Mac khởi động lại):

```bash
make install-autostart     # cài (chạy make up lúc đăng nhập, không mở trình duyệt)
make uninstall-autostart   # gỡ
```

Log: `backend/data/logs/autostart.log`. `make up` / `make down` vẫn dùng bình thường.

### Xem từ điện thoại / máy khác (Tailscale)

1. Cài Tailscale trên Mac (`brew install --cask tailscale-app` hoặc từ tailscale.com) và trên điện thoại; đăng nhập **cùng một tài khoản** ở cả hai.
2. Chạy `make up` trên Mac — lệnh in ra địa chỉ dạng `http://<tên-máy>.<tailnet>.ts.net:3737`.
3. Mở địa chỉ đó trên điện thoại (bật Tailscale). Chỉ thiết bị trong tài khoản Tailscale của bạn vào được; app không mở ra internet công khai.

Mac phải đang bật và không ngủ (System Settings → Displays/Battery → bật "Prevent automatic sleeping when the display is off" khi cắm sạc). Lần đầu macOS có thể hỏi cho phép `node` nhận kết nối — chọn Allow.

Vào **Cài đặt** → thêm keyword (vd `nurse`, `dog mom`) → **Quét ngay** → xem **Best Sellers**.
Velocity/🔥 cần ít nhất 2 lần quét cách nhau ≥ 3 ngày.

### Quét tự động mỗi ngày (macOS)

```bash
make install-daily                    # quét tất cả nguồn lúc 8:00 và 20:00 mỗi ngày (giờ máy)
make install-daily DAILY_HOURS="9"    # đổi giờ (1 hoặc nhiều giờ, cách nhau dấu cách)
make daily-status               # trạng thái + log gần nhất
make scan-now                   # quét ngay trong terminal
make uninstall-daily            # gỡ
```

Sau mỗi lần quét, database được sao lưu vào `backend/data/backups/` (1 bản/ngày, giữ 14 bản; ~30MB/bản). Muốn có bản ngoài máy: đặt `BACKUP_DIR` trong `backend/.env` là một thư mục iCloud Drive. Sao lưu ngay: `make backup`. Khôi phục: tắt app (`make down`), chép bản sao lưu đè lên `backend/data/radar.db`, rồi `make up`.

Dùng launchd: không cần mở backend; nếu máy đang ngủ đúng giờ, macOS chạy bù khi máy thức. Một lần quét ~8–10 phút. Số liệu lưu theo ngày (UTC): lần quét tối cập nhật lại số của ngày đó cho mới hơn, nên mức tăng/ngày vẫn so giữa các ngày. Log: `backend/data/logs/daily-scan.log`.
Khi dùng cách này, đặt `SCHEDULER_ENABLED=false` trong `backend/.env` để backend không quét thêm lần nữa (giờ quét trong trang Cài đặt khi đó không còn tác dụng). Nếu muốn dùng scheduler của backend thay vì launchd: `make uninstall-daily` và đặt `SCHEDULER_ENABLED=true` (backend phải luôn chạy).

## Trend Radar (Phase 2)

Nguồn dữ liệu (chỉ thị trường Mỹ):
- **Etsy** — chỉ shop ở Mỹ, giá USD: lượt xem TB/ngày, số listing mới ≤ 30 ngày, tổng listing (cạnh tranh), tag phổ biến → ngách con.
- **Google gợi ý (US)** — cụm từ người Mỹ gõ sau "<keyword> shirt/hoodie/sweatshirt" → ngách con.
- **Google xu hướng ngày (US)** — sự kiện/tìm kiếm nóng trong ngày (đã lọc theo POD).

Điểm 0–100 = nhu cầu 35% + đà tăng 45% + ít cạnh tranh 20% (chỉnh trong `backend/config/scoring.yaml`).
- Nhu cầu: percentile theo từng nguồn, kéo về 0.5 khi nguồn có < 5 keyword.
- Đà tăng: tăng > 5% → 0.5–1 theo thứ hạng; đi ngang (±5%) → 0.25; giảm → 0; chưa đủ lịch sử → 0.5.
- Cạnh tranh: tương đối giữa các seed, kéo về 0.5 khi < 5 seed.
- Thiếu đà tăng/cạnh tranh được tính trung tính 0.5 (không bị loại), giao diện vẫn hiện "—".

Bộ lọc POD chỉnh trong `backend/config/pod_filter.yaml`. Đà tăng cần ≥ 8 ngày dữ liệu (quét hằng ngày).
Sửa `pod_filter.yaml` / `scoring.yaml` rồi chạy `make rescore` để áp dụng lại bộ lọc và điểm cho dữ liệu hiện có; backend đang chạy tự đọc cấu hình mới ở lần quét tới.

Bấm **+ Theo dõi** ở một ngách khám phá để Etsy quét sản phẩm cho ngách đó từ lần sau.
TikTok Creative Center và Google Trends (biểu đồ quan tâm) chưa hỗ trợ: cả hai chặn truy cập tự động.

## Etsy Listing Signals

Trang **Listing Signals** theo dõi listing áo mới (≤ 30 ngày tuổi) của shop Mỹ trên Etsy (giá USD), cập nhật hằng ngày cho tới khi listing 45 ngày tuổi.
Mỗi listing được xếp vào một nhóm: **Super Breakout**, **Steady Grower**, **Graduated**, **Calibrating** (chưa đủ dữ liệu) hoặc **Đã gỡ** (listing không còn trên Etsy hoặc không còn là áo của shop US, giá USD).
DSR = lượt lưu mới / lượt xem mới giữa hai lần quét.
Ngưỡng phân nhóm và các truy vấn tìm listing chỉnh trong `backend/config/listing_signals.yaml`.
Cần ít nhất 2 lần quét (2 ngày) mới có tín hiệu; lần đầu mọi listing đều là Calibrating.
Tốn khoảng vài trăm request Etsy mỗi ngày, trên quota 5.000/ngày.
Tag của các listing bứt phá được đưa vào Trend Radar với nguồn "Etsy bứt phá".
Chạy riêng: `POST /api/scans` với `{"sources": ["etsy_signals"]}`.


Listing bán **file thiết kế** (PNG/SVG, mockup, digital download, sublimation design, DTF/iron-on transfer — hoặc Etsy ghi `listing_type: download`) bị bỏ qua, không tính là áo; listing đã theo dõi mà là file số sẽ chuyển sang "Đã gỡ" ở lần quét kế tiếp.
## Amazon (bản gọn)

Nguồn **Amazon** (amazon.com, thị trường Mỹ) lấy Best Sellers và New Releases của 8 danh mục áo/hoodie, mỗi danh sách top 100, bằng trình duyệt Chromium tự động (`make install` đã cài Chromium qua Playwright).
- Mỗi lần quét mất ~6 phút.
- Trang **Amazon** hiện thứ hạng theo danh mục/danh sách; sản phẩm có cờ **bản quyền** (tên thương hiệu/IP có thể bị khiếu nại) để bạn tránh.
- Cụm từ phổ biến trong tiêu đề được đưa vào Trend Radar (tín hiệu `title_phrase_count`).
- Chạy riêng: `POST /api/scans` với `{"sources": ["amazon"]}`.
- Cảnh báo: Amazon có thể chặn truy cập tự động (captcha/chặn). Khi đó trạng thái nguồn hiện lỗi, hãy thử lại sau.
- Nguồn này dùng trình duyệt Chromium headless mặc định, nghỉ 4–8 giây giữa trang, dừng ngay khi bị chặn. Việc tự động thu thập dữ liệu trái với Điều khoản sử dụng của Amazon — bạn tự cân nhắc rủi ro; có thể tắt nguồn Amazon trong Cài đặt.

## Lịch mùa vụ (Mỹ)

Trang **Lịch mùa vụ**: các dịp bán áo POD ở Mỹ (lễ lớn, Back to School, Nurses Week, tháng nhận thức, sale TikTok Shop 11.11 / 12.12 / Black Friday / Cyber Monday) với số ngày còn lại, giai đoạn hiện tại và việc nên làm.
Ngoài ra còn có Women's History Month, Earth Day, Cinco de Mayo, Mardi Gras, Juneteenth, Grandparents Day, Hispanic Heritage Month và Día de los Muertos.
Mốc tính lùi: thiết kế −8 tuần, lên sản phẩm −6 tuần, đẩy mạnh −4 tuần, hạn chót giao hàng −10 ngày (in + giao POD).
Mỗi sự kiện gợi ý ghép với seed của bạn (vd "halloween nurse"); các sự kiện sale ghép dạng "<seed> gift" / "<seed> christmas gift". Đồng thời liệt kê keyword liên quan đang có trên Trend Radar.
Chỉnh sự kiện / thời gian giao hàng trong `backend/config/us_calendar.yaml`.

## Watchlist & Tin mới

**Watchlist** (`/watchlist`): các keyword bạn theo dõi. Mỗi keyword là một thẻ: điểm, ngách con tìm được (từ tag Etsy và gợi ý Google), số mẫu Etsy đang Super Breakout / Steady Grower kèm ảnh, nút xem chi tiết và xem listing (trang Etsy bứt phá lọc sẵn theo keyword). Etsy, Google gợi ý và Etsy bứt phá dùng Watchlist để tìm; Amazon và Google xu hướng ngày thì không.

**Tin mới** (`/alerts`): sau mỗi lần quét, app tìm và lưu tin:

| Tin | Khi nào | Phạm vi |
|---|---|---|
| 🚀 Ngách bứt phá | điểm ≥ 60 và tăng trưởng > 20% | keyword trong Watchlist + ngách con |
| 🔥 Etsy bứt phá | listing vừa thành Super Breakout (mọi ngách) hoặc Steady Grower (ngách trong Watchlist) | |
| ⭐ Sản phẩm hot | sản phẩm vừa có nhãn 🔥 ở trang Bán chạy | keyword trong Watchlist |
| 🛒 Amazon mới vào top | lọt top 20 Best Sellers so với ngày quét trước, bỏ hàng có bản quyền | 8 danh mục áo |

Mỗi ngách/sản phẩm chỉ báo 1 lần trong 7 ngày, trừ khi lên mức cao hơn (Steady Grower → Super Breakout). Ngưỡng chỉnh trong `backend/config/alerts.yaml`. Tin ngách bứt phá cần vài ngày dữ liệu để có tăng trưởng.

### Thông báo Telegram

1. Trong Telegram, chat với **@BotFather** → `/newbot` → đặt tên → nhận **token**.
2. Mở chat với bot vừa tạo, gửi 1 tin bất kỳ (vd "hi").
3. Trên Mac: `make telegram-setup` → dán token (không hiện khi gõ). Lệnh tự tìm chat của bạn, hỏi địa chỉ app (mặc định là địa chỉ Tailscale), lưu vào `backend/.env` và gửi tin thử.
4. Khởi động lại backend: `make down && make up`.

Sau mỗi lần quét (8:00 và 20:00), bot gửi **1 thông báo duy nhất** cho cả lần quét: một album ảnh, chú thích liệt kê tối đa 5 tin quan trọng nhất (lý do, link mở trong app), còn lại gom thành dòng "… và N tin khác".

- **Im lặng** (không rung/chuông) trừ khi có tin 🚀 ngách bứt phá hoặc 🔥 Super Breakout.
- **Giờ yên lặng** 22:00–7:00 (giờ máy): không gửi gì, tin được giữ lại và gửi ở lần quét kế tiếp. Chỉnh `quiet_start` / `quiet_end` trong `backend/config/alerts.yaml` (đặt bằng nhau để tắt).
- **Tổng kết tuần**: lần quét đầu tiên mỗi tuần (thường sáng thứ Hai 8:00) gửi thêm 1 tin tổng kết: ngách tăng mạnh nhất 7 ngày, Watchlist (điểm · số listing bứt phá · số tin), sự kiện sắp tới theo lịch mùa vụ, và số tin tuần qua. Xem trước và gửi ngay bằng `make digest-now` (không ảnh hưởng lịch gửi thứ Hai).

Trang Tin mới có nút **Gửi tin thử**. Token chỉ nằm trong `backend/.env`, không hiện ra giao diện hay log. Telegram lỗi không làm hỏng lần quét; tin chưa gửi được sẽ gửi lại ở lần quét sau (trong 2 ngày), tin tổng kết gửi lỗi sẽ thử lại ở lần quét kế tiếp.

## Test

```bash
make test           # backend unit/API tests, không gọi mạng
make smoke          # gọi thật các nguồn đã cấu hình
```

## Lưu ý vận hành
- Luôn chạy backend bằng `make dev-backend` (file `.env` và đường dẫn SQLite được tính tương đối theo thư mục `backend/`).
- Mở dashboard tại http://localhost:3737 (CORS mặc định chỉ cho phép origin này; nếu khác thì đổi `CORS_ORIGINS`).
- API không có xác thực, vì vậy không chạy với `--host 0.0.0.0` trên mạng dùng chung.

## Lưu ý
- Reviews/favorites là chỉ số proxy, không phải doanh số thật.
- Chỉ dùng cho nghiên cứu nội bộ, tần suất thấp, tuân thủ điều khoản API của từng nền tảng.
