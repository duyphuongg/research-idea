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
make dev-backend    # http://localhost:8000  (docs: /docs)
make dev-frontend   # http://localhost:3000
```

Vào **Cài đặt** → thêm keyword (vd `nurse`, `dog mom`) → **Quét ngay** → xem **Best Sellers**.
Scheduler tự quét mỗi ngày theo giờ UTC đã chọn (backend phải đang chạy).

Velocity/🔥 cần ít nhất 2 lần quét cách nhau ≥ 3 ngày.

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

## Test

```bash
make test           # backend unit/API tests, không gọi mạng
make smoke          # gọi thật các nguồn đã cấu hình
```

## Lưu ý vận hành
- Luôn chạy backend bằng `make dev-backend` (file `.env` và đường dẫn SQLite được tính tương đối theo thư mục `backend/`).
- Mở dashboard tại http://localhost:3000 (CORS mặc định chỉ cho phép origin này; nếu khác thì đổi `CORS_ORIGINS`).
- API không có xác thực, vì vậy không chạy với `--host 0.0.0.0` trên mạng dùng chung.

## Lưu ý
- Reviews/favorites là chỉ số proxy, không phải doanh số thật.
- Chỉ dùng cho nghiên cứu nội bộ, tần suất thấp, tuân thủ điều khoản API của từng nền tảng.
