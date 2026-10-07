# POD Trend Radar — UI redesign ("Press Room")

## Brief

Dashboard dùng hằng ngày của một người bán áo POD trên TikTok Shop US (người Việt, UI tiếng Việt), để nhìn ra ngách đáng làm và hành động nhanh. Dữ liệu dày (bảng, thẻ sản phẩm, số liệu). Mỗi trang có một việc chính:
- Trend Radar `/`: chọn ngách để theo dõi/thiết kế.
- Listing Signals `/signals`: tìm mẫu áo mới đang bứt phá trên Etsy.
- Amazon `/amazon`: xem top bán chạy / mới vào top theo danh mục.
- Best Sellers `/products`: sản phẩm bán chạy theo keyword.
- Lịch mùa vụ `/calendar`: biết việc cần làm cho từng dịp.
- Cài đặt `/settings`: watchlist, nguồn, quét.
- Chi tiết keyword `/trends/[id]`.

## Concept: "Press Room" — phòng in

Thế giới của chủ đề là xưởng in áo: mực CMYK, lưới chấm halftone, dấu căn chỉnh (registration mark ⊕), phiếu thông số in (spec sheet), nhãn mác áo. Giao diện như một bàn điều phối in: giấy sáng lạnh, mực đậm, màu nguồn dữ liệu = màu mực in.

### Color tokens (Tailwind v4 `@theme` trong `app/globals.css`)

| Token | Hex | Dùng cho |
|---|---|---|
| `paper` | `#EEF1F4` | nền trang (giấy in lạnh, hơi xanh xám — không phải kem) |
| `sheet` | `#FFFFFF` | thẻ, bảng, panel |
| `ink` | `#15171E` | chữ chính, sidebar, nút chính |
| `ink-2` | `#5B6170` | chữ phụ |
| `rule` | `#D5DAE1` | viền 1px, đường kẻ |
| `cyan` | `#0096B7` | nguồn Etsy / Etsy tag / Etsy bứt phá |
| `magenta` | `#C8246E` | nguồn Amazon; cảnh báo bản quyền |
| `yellow` | `#E3A600` | nguồn Google (gợi ý, xu hướng ngày) |
| `go` | `#1F8A5B` | tăng, ok |
| `stop` | `#C8371D` | giảm, lỗi |

Không dùng gradient. Không dùng shadow lớn; chỉ `shadow-[0_1px_0_#D5DAE1]` cho thẻ. Bo góc 6px (`rounded-md`) cho thẻ/nút, 999px cho chip.

Mapping nguồn → mực (dùng nhất quán mọi nơi, kèm chữ, không chỉ màu): `etsy`, `etsy_tags`, `etsy_signals` → cyan; `amazon` → magenta; `google_suggest`, `google_daily` → yellow.

### Typography (next/font/google, subset `latin` + `vietnamese`)

- Display: **Archivo** (variable, dùng trục width `wdth` 112–125, weight 700–800) — chỉ cho tiêu đề trang, số hạng lớn, nhãn section dạng nhãn mác áo (UPPERCASE, letter-spacing 0.08em, cỡ 11px cho eyebrow). Dùng tiết chế.
- Body/UI: **Be Vietnam Pro** (400/500/600) — thiết kế cho tiếng Việt, mọi văn bản giao diện.
- Data: **IBM Plex Mono** (400/500) — số liệu, điểm, ASIN, ngày, delta; luôn `tabular-nums`.
- Scale: eyebrow 11px · body 14px · small 12px · h2 18px · page title 28px (Archivo 800, wdth 112) · big numerals 32px mono.

### Layout

```
┌──────────┬─────────────────────────────────────────────┐
│ ⊕ POD    │ ⊕ TREND RADAR · 07/10/2026 (eyebrow)        │
│ TREND    │ Ngách đang lên                  [actions]   │
│ RADAR    │ one-line description (ink-2)                │
│──────────│─────────────────────────────────────────────│
│ Radar    │ [filters bar: sheet, 1px rule]              │
│ Signals  │ ┌ content (sheet cards / tables) ────────┐  │
│ Amazon   │ │                                        │  │
│ Bán chạy │ └────────────────────────────────────────┘  │
│ Lịch     │                                             │
│ Cài đặt  │                                             │
│──────────│                                             │
│ BẢN IN   │                                             │
│ hôm nay  │                                             │
│ C M Y K  │                                             │
│ 08:00 ✓  │                                             │
└──────────┴─────────────────────────────────────────────┘
```

- Sidebar cố định 232px, nền `ink`, chữ trắng/xám nhạt; mục active có thanh mực 3px bên trái + chữ trắng đậm. Dưới cùng: **"Bản in hôm nay"** — trạng thái quét của từng nguồn dạng 4 ô mực nhỏ (C/M/Y/K) với ✓/✕ và giờ quét gần nhất (từ `/api/health/sources`).
- Mobile (< 1024px): sidebar thành top bar (logo + nút menu mở drawer). Nội dung 1 cột, bảng cuộn ngang trong khung riêng (không cuộn cả trang).
- Main: max-width 1280px, padding 32px (desktop) / 16px (mobile). Page header: eyebrow (⊕ + tên trang + ngày dữ liệu), tiêu đề (Archivo), mô tả 1 dòng, actions bên phải.

### Signature: halftone meter

Điểm (0–100), DSR, nhu cầu… hiển thị bằng **thước chấm halftone**: 10 chấm tròn xếp hàng, kích thước chấm tăng dần theo giá trị (chấm "đầy" = mực ink, chấm chưa đạt = viền rule), kèm số mono bên cạnh. Component `HalftoneMeter value(0..1) size="sm|md"`. Đây là điểm nhấn duy nhất — mọi thứ khác yên tĩnh.

Phụ: dấu ⊕ (registration mark, SVG 12px) trước eyebrow mỗi trang và trong logo.

### Components (frontend/components/ui/)

- `AppShell` (sidebar + mobile top bar/drawer + main), `PressStatus` (khối "Bản in hôm nay").
- `PageHeader {eyebrow, title, description, actions}`.
- `Card`, `Section {title, aside}`.
- `SourceChip {source}` (chấm mực + nhãn), `InkDot`.
- `HalftoneMeter`.
- `Delta {value, unit}` (▲ go / ▼ stop / — ink-2, mono).
- `StatusBadge` (cho trạng thái quét, nhóm Listing Signals, giai đoạn lịch).
- `Button` (primary ink / secondary sheet+rule / ghost), `Select`, `Checkbox`, `Tabs` (gạch chân mực 2px), `EmptyState {title, body, action}`, `Notice {tone}`.
- Giữ `Sparkline` (đổi màu sang ink/go/stop).

### Page treatments

- **Trend Radar**: bảng dày đặc trên `sheet`: hạng (mono), keyword (Be Vietnam Pro 600) + nhãn Mới/seed, cột **Điểm** = HalftoneMeter + số, Tăng trưởng = Delta, Nguồn = SourceChip, 30 ngày = Sparkline, nút "Theo dõi". Dải "Sắp tới" thành hàng chip lịch phía trên bảng (ngày còn lại mono + giai đoạn).
- **Chi tiết keyword**: header + 5 ô số (Điểm, Nhu cầu, Đà tăng, Cạnh tranh, Tăng trưởng) dạng spec sheet (nhãn eyebrow + số mono lớn + HalftoneMeter cho 3 thành phần); biểu đồ Recharts màu theo mực nguồn; keyword liên quan = chip; sản phẩm = grid thẻ.
- **Listing Signals**: tabs trạng thái có số đếm; thẻ: ảnh 4:5, nhãn trạng thái góc trái, tuổi + giá mono, tiêu đề 2 dòng, hàng số "VIEWS / LƯU / DSR" dạng spec (eyebrow + mono), DSR có HalftoneMeter nhỏ, tag chip (link sang Trend Radar).
- **Amazon**: chọn danh mục (segmented), tabs Best Sellers/New Releases; danh sách hàng: số hạng lớn Archivo mono-like, Delta hạng, ảnh 56px, tiêu đề, sao/reviews mono, nhãn "Mới vào top" (cyan) và "Có thể có bản quyền" (magenta outline).
- **Best Sellers**: thanh lọc; grid thẻ sản phẩm cùng hệ thẻ Signals.
- **Lịch mùa vụ**: timeline dọc theo ngày: cột trái ngày (mono, "còn 26 ngày"), cột phải thẻ sự kiện: tên (Archivo), StatusBadge giai đoạn, lời khuyên, mốc (chỉ mốc tương lai), chip ghép ngách + Theo dõi.
- **Cài đặt**: 3 section (Watchlist, Nguồn dữ liệu, Lịch sử quét) trong Card; bảng lịch sử quét có StatusBadge.

### Copy

Giữ tiếng Việt, câu ngắn, động từ rõ ("Theo dõi", "Quét ngay", "Ẩn sản phẩm có bản quyền"). Trạng thái rỗng chỉ dẫn việc cần làm. Giữ nguyên các ghi chú proxy/bản quyền/ToS đã có.

### Quality floor

Responsive tới 360px; focus ring 2px `ink` + offset 2px trên mọi phần tử tương tác; `prefers-reduced-motion` tắt transition; tương phản AA; không đổi API/logic dữ liệu (chỉ trình bày). Lint + build sạch.
