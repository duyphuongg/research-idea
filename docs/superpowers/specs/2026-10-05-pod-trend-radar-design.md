# POD Trend Radar — Design Spec

- **Ngày:** 2026-10-05
- **Trạng thái:** Đã duyệt thiết kế, chờ review spec
- **Người dùng:** Seller POD (t-shirt, sweatshirt, hoodie) bán trên TikTok Shop US

## 1. Mục tiêu

Xây dựng ứng dụng web giúp phát hiện **ngách/keyword đang trending** và **sản phẩm áo đang bán chạy** tại thị trường Mỹ, bằng cách tổng hợp dữ liệu công khai từ nhiều nguồn và chéo kiểm tra.

### Phạm vi MVP
1. **Trend Radar** — phát hiện & xếp hạng keyword đang nổi (từ watchlist seed + keyword mới tự khám phá).
2. **Best Sellers Tracker** — theo dõi top t-shirt/sweatshirt/hoodie trên Etsy & Amazon theo keyword, phát hiện sản phẩm tăng trưởng nhanh qua snapshot hằng ngày.

### Ngoài phạm vi MVP (giai đoạn sau)
- Gợi ý ý tưởng/slogan/prompt thiết kế bằng AI
- Lịch mùa vụ Mỹ
- Đăng nhập / nhiều người dùng (làm khi deploy server)
- Connector trả phí TikTok Shop (FastMoss, Kalodata, EchoTik)
- Redbubble connector

### Triển khai
Giai đoạn 1 chạy local (localhost). Giai đoạn 2 deploy server (VPS/cloud) với quét tự động hằng ngày. Thiết kế phải chuyển được SQLite → Postgres chỉ bằng đổi `DATABASE_URL`.

## 2. Stack

- **Backend:** Python 3.12, FastAPI, SQLAlchemy 2.x + Alembic, SQLite (→ Postgres), APScheduler, httpx, Pydantic v2, pytest
- **Frontend:** Next.js (App Router) + TypeScript + Tailwind, Recharts cho biểu đồ
- **Dịch vụ ngoài:** Etsy Open API v3 (key miễn phí), Apify (Amazon), tùy chọn SerpApi (Google Trends fallback)

## 3. Kiến trúc

```
Scheduler (APScheduler, hằng ngày + "Quét ngay")
   └─► Connectors (mỗi nguồn 1 module, chung interface)
          ├─ tiktok_cc      : hashtag/keyword/top products trending (US)
          ├─ google_trends  : interest over time + rising queries (geo=US)
          ├─ pinterest      : trending keywords (US)
          ├─ etsy           : listings theo keyword (giá, favorites, ngày tạo, ảnh, shop)
          └─ amazon (Apify) : top t-shirt/hoodie theo keyword (BSR, reviews, giá, ảnh)
   └─► Raw store (raw JSON, giữ 30 ngày)
   └─► Normalizer → trend_signals, products, product_snapshots
   └─► Analyzer   → keyword_scores, product hot flags
FastAPI (REST) ──► Next.js dashboard
```

### 3.1 Connector interface

```python
class Connector(Protocol):
    name: str                       # "etsy", "tiktok_cc", ...
    kind: Literal["trend", "product", "both"]
    def enabled(self, settings) -> bool: ...
    async def fetch(self, keywords: list[str]) -> RawBatch: ...
    def normalize(self, raw: RawBatch) -> NormalizedBatch: ...
```

- `fetch` chỉ lấy dữ liệu & trả raw; `normalize` là hàm thuần (dễ test bằng fixture).
- Mỗi connector có rate limiter riêng và retry tối đa 3 lần với exponential backoff.
- Connector lỗi không ảnh hưởng connector khác; lỗi được ghi vào `scan_runs`.
- Thêm nguồn mới = thêm một module + đăng ký vào registry.

### 3.2 Nguồn dữ liệu & mức ổn định

| Nguồn | Cách lấy | Độ ổn định | Dữ liệu chính |
|---|---|---|---|
| Etsy | Open API v3 `findAllListingsActive` | Cao | title, price, num_favorers, created, image, shop, url |
| TikTok Creative Center | Endpoint JSON nội bộ (hashtag, keyword insights, top products), region=US | Trung bình | hashtag/keyword, views, post count, trend curve |
| Google Trends | Thư viện fork của pytrends; fallback SerpApi | Trung bình | interest over time, rising/top related queries |
| Pinterest Trends | Endpoint nội bộ trends.pinterest.com, region US | Trung bình | trending keyword, mức tăng tuần/tháng |
| Amazon | Apify actor (search + product) | Cao (phụ thuộc Apify) | title, price, reviews, rating, BSR, image, url |

Các nguồn "Trung bình" dùng endpoint không chính thức: có thể đổi cấu trúc bất kỳ lúc nào → phát hiện qua `make smoke` và cảnh báo trên dashboard.

## 4. Mô hình dữ liệu

| Bảng | Cột chính |
|---|---|
| `seeds` | id, keyword, active, created_at |
| `keywords` | id, text (chuẩn hóa lowercase), first_seen_at, is_pod_relevant, origin (`seed` \| `discovered`) |
| `trend_signals` | id, keyword_id, source, metric (`interest`, `views`, `posts`, `growth`…), value, date — unique(keyword_id, source, metric, date) |
| `products` | id, source, external_id, title, url, image_url, shop_name, price, product_type (`tshirt` \| `sweatshirt` \| `hoodie` \| `other`), listed_at — unique(source, external_id) |
| `product_keywords` | product_id, keyword_id, rank |
| `product_snapshots` | product_id, date, reviews, favorites, rating, bsr, price — unique(product_id, date) |
| `keyword_scores` | keyword_id, date, demand, momentum, competition, sources_rising, score |
| `saved_products` | product_id, note, created_at (moodboard) |
| `scan_runs` | id, source, started_at, finished_at, status (`ok` \| `partial` \| `failed`), records, error |
| `raw_payloads` | id, scan_run_id, source, fetched_at, payload (JSON) — xóa sau 30 ngày |
| `settings` | key, value (API key, lịch quét, bật/tắt connector, trọng số) |

API key lưu trong `.env` (ưu tiên) hoặc bảng `settings`; không bao giờ trả API key về frontend (chỉ trả trạng thái "đã cấu hình").

## 5. Phân tích

### 5.1 Lọc POD
Keyword được đánh dấu `is_pod_relevant` dựa trên:
- Danh sách chặn (blocklist) các nhóm không in áo được: điện tử, mỹ phẩm, thực phẩm, thuốc, linh kiện…
- Danh sách tín hiệu tích cực: nghề nghiệp, sở thích, thú cưng, vai trò gia đình (mom/dad/grandma), sự kiện/mùa, câu nói/meme, thể thao.
- Keyword từ seed luôn được coi là relevant.
- Danh sách nằm trong file config YAML để chỉnh sửa. (AI phân loại: giai đoạn sau.)

### 5.2 Điểm cơ hội keyword (0–100)

Ba thành phần, mỗi thành phần chuẩn hóa 0–1 bằng percentile rank trên toàn bộ keyword của ngày quét:

- **Demand:** trung bình các chỉ số phổ biến hiện tại có sẵn (Google interest, TikTok views, Pinterest volume).
- **Momentum:** với mỗi nguồn, `growth = mean(7 ngày gần nhất) / mean(30 ngày gần nhất) − 1`; lấy trung bình các nguồn có dữ liệu. Thưởng hội tụ: `+0.1` cho mỗi nguồn thứ 2 trở đi có growth > 0.2 (cắt ở 1.0 sau khi chuẩn hóa).
- **Competition:** số listing Etsy + số kết quả Amazon cho `"<keyword> shirt"`, chuẩn hóa log.

```
score = 100 × (w_d·Demand + w_m·Momentum + w_c·(1 − Competition))
mặc định: w_d = 0.35, w_m = 0.45, w_c = 0.20  (config được)
```

Nguồn thiếu dữ liệu → thành phần tính trên các nguồn còn lại, không tính là 0. Keyword có dữ liệu từ < 1 nguồn trong 7 ngày → không chấm điểm.

Keyword có `first_seen_at` trong 7 ngày gần nhất → gắn nhãn **Mới**.

### 5.3 Sản phẩm "hot"

```
velocity = Δ(reviews hoặc favorites) trong 7 ngày / max(1, số tuần từ listed_at)
```
Top 10% velocity theo từng nguồn & product_type → gắn 🔥. Cần ít nhất 2 snapshot cách nhau ≥ 3 ngày mới tính. Dashboard ghi rõ đây là **proxy**, không phải doanh số thật.

## 6. API (FastAPI)

| Method | Path | Mô tả |
|---|---|---|
| GET | `/api/trends?days=7&source=&pod_only=true&limit=` | Danh sách keyword xếp hạng + sparkline 30 ngày |
| GET | `/api/trends/{keyword_id}` | Chi tiết: signals theo nguồn, related keywords, competition, top products |
| GET | `/api/products?source=&type=&keyword_id=&sort=velocity\|reviews\|price\|newest` | Lưới best sellers |
| POST/DELETE | `/api/products/{id}/save` | Lưu/bỏ lưu moodboard |
| GET | `/api/saved` | Moodboard |
| GET/POST/DELETE | `/api/seeds` | Quản lý watchlist |
| GET/PUT | `/api/settings` | Bật/tắt connector, lịch quét, trọng số, trạng thái API key |
| POST | `/api/scans` | Quét ngay (toàn bộ hoặc 1 nguồn), chạy nền |
| GET | `/api/scans?limit=` | Lịch sử & trạng thái quét |
| GET | `/api/health/sources` | Trạng thái lần quét gần nhất của từng nguồn (cho banner cảnh báo) |

## 7. Màn hình (Next.js)

1. **Trend Radar (`/`)** — bảng keyword: điểm, momentum %, badge nguồn đang tăng, sparkline 30d, nhãn "Mới"; lọc theo khoảng thời gian, nguồn, POD-only; nút "+ Theo dõi" (thêm seed), "Xem chi tiết". Banner cảnh báo nguồn lỗi.
2. **Chi tiết keyword (`/trends/[id]`)** — biểu đồ chồng momentum theo nguồn, related keywords, chỉ số cạnh tranh, lưới top sản phẩm của keyword.
3. **Best Sellers (`/products`)** — lưới card (ảnh, title, giá, reviews/favorites + Δ7d, 🔥, shop, ngày đăng); lọc nguồn/loại áo/keyword; sắp xếp; mở link gốc; nút Lưu.
4. **Moodboard (`/saved`)** — sản phẩm đã lưu kèm ghi chú.
5. **Cài đặt (`/settings`)** — watchlist seed, bật/tắt connector, trạng thái API key, lịch quét, trọng số điểm, "Quét ngay", log quét.

## 8. Xử lý lỗi

- Retry 3 lần, exponential backoff, rate limit theo nguồn.
- Mỗi lần quét ghi `scan_runs`; `partial` khi một số keyword lỗi.
- Một connector lỗi không chặn pipeline; Analyzer chạy trên dữ liệu có sẵn.
- Raw JSON giữ 30 ngày để re-normalize/re-score mà không cần quét lại (`make rescore`).
- Thiếu API key → connector tự tắt, dashboard hiển thị "chưa cấu hình".

## 9. Kiểm thử

- **Connector:** `normalize()` test bằng fixture JSON thật lưu trong `tests/fixtures/<source>/`; không gọi mạng trong test.
- **Analyzer:** unit test với dữ liệu tổng hợp — percentile, momentum, thưởng hội tụ, xử lý nguồn thiếu, velocity, bộ lọc POD.
- **API:** test endpoint bằng FastAPI TestClient + SQLite in-memory.
- **Smoke:** `make smoke` gọi thật từng nguồn với 1 keyword, in kết quả; chạy thủ công.

## 10. Cấu trúc thư mục

```
backend/
  app/
    main.py            # FastAPI app
    config.py          # settings từ .env + YAML
    db.py, models.py
    connectors/        # base.py, registry.py, etsy.py, tiktok_cc.py, google_trends.py, pinterest.py, amazon_apify.py
    pipeline/          # scan.py (orchestrate), normalize.py
    analysis/          # pod_filter.py, scoring.py, velocity.py
    api/               # trends.py, products.py, seeds.py, settings.py, scans.py
    scheduler.py
  config/pod_filter.yaml, scoring.yaml
  tests/
  alembic/
frontend/
  app/ (/, /trends/[id], /products, /saved, /settings)
  components/, lib/api.ts
Makefile, .env.example, README.md
```

## 11. Thứ tự xây dựng

1. **Nền tảng + Etsy:** khung backend (models, migrations, scan pipeline, scheduler), connector Etsy, snapshot & velocity, API products, màn Best Sellers + Settings tối thiểu.
2. **Trend Radar:** connector TikTok Creative Center + Google Trends, POD filter, scoring, API trends, màn Trend Radar.
3. **Mở rộng:** connector Pinterest + Amazon (Apify), màn chi tiết keyword, Moodboard, Settings đầy đủ.

## 12. Rủi ro

- Endpoint không chính thức (TikTok CC, Pinterest, Google Trends) có thể thay đổi/chặn → connector cô lập, smoke test, cảnh báo dashboard.
- Điều khoản sử dụng của các nền tảng: chỉ dùng cho nghiên cứu nội bộ, tần suất thấp (1 lần/ngày), tôn trọng rate limit.
- Proxy doanh số (reviews/favorites) không phản ánh chính xác doanh thu → ghi chú rõ trên UI.
- Chi phí Apify vượt free tier nếu quét nhiều keyword → giới hạn số keyword/sản phẩm cho Amazon trong settings.
