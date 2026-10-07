# POD Trend Radar — Amazon Lite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Chụp hằng ngày Amazon Best Sellers + New Releases của 8 danh mục áo Novelty (top 100), theo dõi thay đổi hạng / sản phẩm mới vào top, gắn cờ bản quyền, và đưa cụm từ tiêu đề thành nguồn ngách cho Trend Radar.

**Architecture:** Connector `amazon` (kind product) dùng Playwright qua một `page_loader` có thể thay thế (test dùng loader giả). Parse thuần từ danh sách item thô → `NormalizedProduct` (source amazon) + `NormalizedRank` (bảng `amazon_ranks`) + tín hiệu cụm từ. API `/api/amazon`, trang `/amazon`.

**Spec:** `docs/superpowers/specs/2026-10-05-pod-trend-radar-design.md` §16.

## Global Constraints

- Danh mục (key → node, product_type): `women_tshirts` 9056923011 tshirt; `men_tshirts` 9056987011 tshirt; `women_hoodies` 9056928011 hoodie; `women_sweatshirts` 9056929011 sweatshirt; `men_hoodies` 9056992011 hoodie; `men_sweatshirts` 9056993011 sweatshirt; `boys_tops` 9057093011 tshirt; `girls_tops` 9057039011 tshirt.
- Danh sách: `bestsellers` → `https://www.amazon.com/gp/bestsellers/fashion/{node}?pg={page}`; `new_releases` → `https://www.amazon.com/gp/new-releases/fashion/{node}?pg={page}`; pages 1–2.
- Nghỉ ngẫu nhiên 4–8 giây giữa các trang. Bị chặn = HTTP ≥ 400, hoặc nội dung chứa "captcha" / "Enter the characters you see" / "Sorry! Something went wrong", hoặc 0 item → lỗi `"{category}/{list}/p{page}: blocked"`; 2 trang bị chặn liên tiếp → dừng phần còn lại với lỗi "aborted: Amazon is blocking requests".
- Không lưu giá (VND). `url = https://www.amazon.com/dp/{asin}`.
- Cờ bản quyền theo `backend/config/amazon.yaml` (`licensed_terms`, so khớp nguyên từ, không phân biệt hoa thường). Sản phẩm licensed không đóng góp cụm từ cho Trend Radar.
- Tín hiệu: cụm 2–3 từ (token chữ/số, lowercase), bỏ cụm toàn từ trong `STOPWORDS ∪ APPAREL_WORDS ∪ GENERIC_WORDS` hoặc bắt đầu/kết thúc bằng stopword; đếm 1 lần/sản phẩm; giữ cụm có ≥ 3 sản phẩm (`min_phrase_products`), tối đa 40 (`max_phrases`), ưu tiên cụm dài hơn khi cùng số đếm và bỏ cụm 2 từ nằm trong một cụm 3 từ đã giữ có cùng số đếm. `source="amazon"`, `metric="title_phrase_count"`, origin discovered, nguồn tin cậy.
- Không gọi mạng / không mở trình duyệt trong pytest. Commit trailer: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

---

### Task 1: Schema, contracts, store

**Files:** `backend/app/models.py`, `backend/app/connectors/base.py`, `backend/app/pipeline/store.py`, migration (autogenerate), tests in `test_models.py` / `test_store.py`.

**Interfaces:**
- `AmazonRank(id, product_id FK, date, category_key String(40), list_name String(20), rank Integer)` unique (product_id, date, category_key, list_name).
- `Product.licensed: bool | None` (nullable Boolean).
- `NormalizedProduct.licensed: bool | None = None` (append last).
- `NormalizedRank(external_id: str, category_key: str, list_name: str, rank: int, date: date)` dataclass; `NormalizedBatch.ranks: list[NormalizedRank] = field(default_factory=list)`.
- `persist_batch` also upserts ranks: product looked up by (source "amazon", external_id); skip if missing; upsert on the unique key (update rank). Returns count including ranks. `upsert_product` sets `product.licensed` when `item.licensed is not None`.

- [ ] TDD: model test (unique constraint), store test (product + rank persisted; re-persisting same day updates rank; rank for unknown ASIN skipped; licensed flag stored).
- [ ] Migration: only `amazon_ranks` + `products.licensed`; `alembic upgrade head` on dev DB.
- [ ] Commit `feat(backend): add amazon ranks table and licensed flag`.

---

### Task 2: Amazon config + pure parsing (titles, licensing, phrases)

**Files:** create `backend/config/amazon.yaml`, `backend/app/analysis/amazon.py`; test `backend/tests/test_amazon_analysis.py`.

**Interfaces:**
- `AmazonCategory(key, node, product_type)`; `AmazonConfig(categories: tuple[AmazonCategory, ...], lists: tuple[str, ...] = ("bestsellers", "new_releases"), pages: int = 2, delay_seconds: tuple[float, float] = (4.0, 8.0), licensed_terms: tuple[str, ...], min_phrase_products: int = 3, max_phrases: int = 40)`; `load_amazon_config()`.
- `list_url(list_name, node, page) -> str`.
- `is_licensed(title, terms) -> bool` (whole-word/phrase, case-insensitive).
- `parse_reviews(text) -> int | None` ("2,959" → 2959; "1.2K" → 1200; junk → None); `parse_rating(text) -> float | None` ("4.6 out of 5 stars" → 4.6).
- `title_phrases(titles: list[str], min_products, max_phrases) -> list[tuple[str, int]]` per Global Constraints. `STOPWORDS = {"a","an","and","for","of","the","to","with","in","on","my","your","is","it","this","that","i","you","me","men","mens","women","womens","kids","boys","girls","youth","adult","unisex"}`.

`amazon.yaml`:

```yaml
# Amazon Best Sellers / New Releases — danh mục áo Novelty (thị trường Mỹ).
lists: [bestsellers, new_releases]
pages: 2                 # 50 sản phẩm / trang → top 100
delay_seconds: [4, 8]    # nghỉ ngẫu nhiên giữa các trang để tránh bị chặn
min_phrase_products: 3
max_phrases: 40
categories:
  - {key: women_tshirts, node: "9056923011", product_type: tshirt}
  - {key: men_tshirts, node: "9056987011", product_type: tshirt}
  - {key: women_hoodies, node: "9056928011", product_type: hoodie}
  - {key: women_sweatshirts, node: "9056929011", product_type: sweatshirt}
  - {key: men_hoodies, node: "9056992011", product_type: hoodie}
  - {key: men_sweatshirts, node: "9056993011", product_type: sweatshirt}
  - {key: boys_tops, node: "9057093011", product_type: tshirt}
  - {key: girls_tops, node: "9057039011", product_type: tshirt}
# Thương hiệu / IP có bản quyền hoặc áo trơn thương hiệu — gắn cờ, không đưa vào Trend Radar.
licensed_terms: [disney, marvel, star wars, pixar, harry potter, hogwarts, nfl, nba, mlb, nhl, ncaa, notre dame, superman, batman, dc comics, justice league, spider-man, spiderman, avengers, pokemon, nintendo, mario, zelda, minecraft, roblox, fortnite, peanuts, snoopy, looney tunes, hello kitty, sanrio, barbie, sesame street, paw patrol, bluey, stranger things, friends tv, the office, grateful dead, rolling stones, ac/dc, nirvana, coca-cola, jeep, ford, chevy, harley, true classic, hanes, gildan, fruit of the loom, champion, nike, adidas, under armour, carhartt, amazon essentials, comfort colors]
```

Tests (examples, must be in the test file): `is_licensed("Popfunk Superman Classic Logo T-Shirt", terms)` True; `is_licensed("Retro Superb Mom Shirt", terms)` False (no partial "superb"→"superman"); `parse_reviews(" 2,959")==2959`, `parse_reviews("1.2K")==1200`; `parse_rating("4.6 out of 5 stars")==4.6`; `title_phrases` on titles ["Funny Pickleball Shirt Gift", "Pickleball Mom Funny Pickleball T-Shirt", "I Love Pickleball Funny Pickleball Tee", "Spooky Season Ghost Shirt"] with min 3 → contains ("funny pickleball", 3) and not "shirt"-only phrases, not ("pickleball", ...) single words.

- [ ] TDD; commit `feat(analysis): amazon config, licensing and title phrases`.

---

### Task 3: Amazon connector (Playwright loader + parse + normalize)

**Files:** create `backend/app/connectors/amazon.py`; tests `backend/tests/test_amazon_connector.py` with a fixture `backend/tests/fixtures/amazon/page_items.json` (list of raw item dicts as the extractor returns them).

**Interfaces:**
- `PageResult(status: int, text_sample: str, items: list[dict])` where item dict keys: `rank` ("#12"), `href`, `title`, `img`, `rating` ("4.6 out of 5 stars" | None), `reviews` (text | None).
- `PageLoader = Callable[[str], Awaitable[PageResult]]`.
- `PlaywrightLoader` — async context manager; launches Chromium headless (`locale="en-US"`, desktop Chrome UA, viewport 1400×2400); `__call__(url)` goes to the URL (`wait_until="domcontentloaded"`, timeout 45s), scrolls 6× (3000px, 700ms), extracts items with the JS below from `div[id^='p13n-asin-index']` (fallback `div[data-asin]`), returns `PageResult(status, first 2000 chars of body text, items)`. Import playwright lazily inside the class so the app imports without it.

```js
els => els.map(e => {
  const a = e.querySelector('a[href*="/dp/"]');
  const img = e.querySelector('img');
  const rank = e.querySelector('.zg-bdg-text');
  const rating = e.querySelector('i[class*="a-icon-star"] span, .a-icon-alt');
  const reviews = e.querySelector('a[href*="product-reviews"] span');
  return {rank: rank && rank.innerText, href: a && a.getAttribute('href'),
          title: img && img.getAttribute('alt'), img: img && img.getAttribute('src'),
          rating: rating && rating.innerText, reviews: reviews && reviews.innerText};
})
```

- `AmazonConnector(config=None, *, loader_factory=PlaywrightLoader, sleep=asyncio.sleep, rng=random.Random())`; `name="amazon"`, `kind="product"`; `enabled()` True iff playwright is importable (`importlib.util.find_spec("playwright") is not None`).
- `fetch(keywords)` (keywords ignored): for each category × list × page, `await sleep(rng.uniform(*delay))` between pages (not before the first), load, detect block per Global Constraints, else payload `{"category": key, "list": list_name, "page": page, "items": [...]}`; errors per page; abort after 2 consecutive blocked pages. Loader exceptions count as blocked.
- `normalize(raw, today)`: dedupe items by ASIN within a payload (`/dp/(B0[A-Z0-9]{8})` from href); rank = int from "#N"; per item → `NormalizedProduct(source="amazon", external_id=asin, title=title, url=f"https://www.amazon.com/dp/{asin}", image_url=img, shop_name=None, price=None, currency=None, product_type=category.product_type, listed_at=None, keyword=None, rank=rank, reviews=parse_reviews(...), rating=parse_rating(...), bsr=rank if list == "bestsellers" else None, licensed=is_licensed(title, terms))` (one product per ASIN per batch: keep the best bestsellers rank) and `NormalizedRank(asin, category, list, rank, today)` for every (asin, category, list); signals = `title_phrases` of non-licensed titles (deduped by ASIN) → `NormalizedSignal(keyword=phrase, source="amazon", metric="title_phrase_count", value=count, date=today, origin="discovered")`.

Tests: normalize from fixture (dedupe, ranks, licensed flag, bsr only for bestsellers, phrases); fetch with a fake loader returning results per URL — happy path (payload count = categories×lists×pages using a 1-category config), sleep called between pages with values in [4, 8], a blocked page (captcha text) recorded as error, 2 consecutive blocked → abort error and no further loads.

- [ ] TDD; commit `feat(connectors): add Amazon best sellers connector`.

---

### Task 4: Wiring (registry, trusted source, scoring, dependency)

- `backend/pyproject.toml`: add `"playwright>=1.47"` to dependencies; root `Makefile` `install` target: after pip install, run `cd backend && .venv/bin/python -m playwright install chromium`.
- Registry: append `AmazonConnector()` to `make_all_connectors` (after google_daily). `connector_status` shows it (configured = playwright importable).
- `TRUSTED_SOURCES` += "amazon"; scoring `PRIMARY_METRICS["amazon"] = "title_phrase_count"`.
- Products API: no change needed (source "amazon" filter works); velocity uses reviews.
- Update tests that list connectors (registry, settings defaults, health) — amazon appears after google_daily; use `configured` according to whether playwright is installed in the venv (it will be after this task's install), or assert by name lookup. Make sure no test launches a browser: connectors in API tests come from fake factories; add a test that `build_connectors` includes "amazon" without instantiating a browser (constructor must not start Playwright).
- [ ] Install: `uv pip install --python backend/.venv/bin/python -e "backend[dev]"` and `backend/.venv/bin/python -m playwright install chromium`.
- [ ] Full suite; commit `feat(scan): register Amazon connector and feed title phrases to Trend Radar`.

---

### Task 5: Amazon API

**Files:** `backend/app/api/amazon.py`, schemas, main.py router; test `backend/tests/test_api_amazon.py`.

`GET /api/amazon?category=<key>&list=bestsellers|new_releases&hide_licensed=false` (category default first config category; 422 for unknown category/list) → `AmazonPage {date: date | null, category, list, categories: [{key, product_type}], items: [AmazonItem]}`; date = latest AmazonRank.date for that category/list; items sorted by rank; `AmazonItem {product_id, asin, rank, prev_rank: int | null (rank on the most recent earlier date for same category/list), rank_change: int | null (prev_rank − rank; positive = moved up), is_new_entry (no earlier row for this category/list within the last 7 days), title, url, image_url, rating, reviews, product_type, licensed}`.

Tests: two dates of ranks → rank_change and is_new_entry correct; hide_licensed filters; unknown category → 422; empty → date null, items [].
- [ ] TDD; commit `feat(api): add Amazon ranks endpoint`.

---

### Task 6: Amazon page + Best Sellers source option

- `frontend/lib/api.ts`: types + `api.getAmazon(q)`.
- `frontend/app/amazon/page.tsx`: category select (Vietnamese labels: Áo thun nữ, Áo thun nam, Hoodie nữ, Sweatshirt nữ, Hoodie nam, Sweatshirt nam, Áo bé trai, Áo bé gái), list tabs (Best Sellers / New Releases), checkbox "Ẩn sản phẩm có bản quyền"; table/grid rows: rank, change (▲N green / ▼N red / "Mới" badge), image, title (link to Amazon, new tab), rating ★, reviews, ⚠️ "Có thể có bản quyền — đừng sao chép" for licensed; note "Dữ liệu từ trang Best Sellers / New Releases công khai của Amazon (Mỹ), cập nhật mỗi lần quét. Hạng là trong danh mục, không phải doanh số."; empty/blocked state referencing source health.
- Nav link "Amazon" after "Listing Signals"; `/products` source select adds `<option value="amazon">Amazon</option>`; `SOURCE_LABEL.amazon = "Amazon"`, `METRIC_LABEL.title_phrase_count = "Số sản phẩm Amazon top có cụm từ"`.
- [ ] lint + build; commit `feat(frontend): add Amazon page`.

---

### Task 7: README + live run (real Amazon)

- README section "Amazon (bản gọn)" (Vietnamese): sources, 8 categories, top 100, ~4–5 phút/lần quét, cờ bản quyền, cảnh báo có thể bị Amazon chặn (trạng thái nguồn hiện lỗi), `make install` cài Chromium.
- Live: `make migrate`; start backend; `POST /api/scans {"sources": ["amazon"]}`; poll until done (timeout 15 min); report run status/records/error and whether any page was blocked; counts of amazon products, ranks per category/list, licensed count, top 10 title phrases (sqlite read-only); `GET /api/amazon?category=women_tshirts&list=bestsellers` (trim); frontend `/amazon` 200. Stop servers.
- If Amazon blocks (run failed with "blocked"), report it clearly — do not try to evade blocking.
- [ ] Commit `docs: document Amazon lite`.
