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
