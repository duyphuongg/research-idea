# POD Trend Radar

Ứng dụng nghiên cứu ngách & sản phẩm POD (t-shirt, sweatshirt, hoodie) bán chạy tại Mỹ.
Phase 1: connector Etsy, theo dõi Best Sellers (snapshot hằng ngày, tăng trưởng 7 ngày, 🔥), trang Cài đặt.

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
