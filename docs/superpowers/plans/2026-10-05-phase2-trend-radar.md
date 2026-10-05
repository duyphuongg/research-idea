# POD Trend Radar — Phase 2 (Trend Radar) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Phát hiện và xếp hạng ngách POD đang nổi tại Mỹ từ Etsy (shop US), Google Autocomplete (US) và Google Daily Trends (US); hiển thị trên màn Trend Radar + trang chi tiết keyword.

**Architecture:** Thêm 2 connector (google_suggest, google_daily) cùng interface Phase 1; Etsy connector lọc shop US, sinh tín hiệu cấp keyword và khám phá tag. Tín hiệu lưu `trend_signals`; quan hệ seed→ngách con lưu `keyword_relations`; module chấm điểm thuần tính `keyword_scores` sau mỗi lần quét. API `/api/trends` phục vụ dashboard.

**Tech Stack:** như Phase 1 + PyYAML (backend), Recharts (frontend).

**Spec:** `docs/superpowers/specs/2026-10-05-pod-trend-radar-design.md` — mục 13 (cập nhật Phase 2) thay thế các phần Phase 2 cũ.

## Global Constraints

- Tất cả ràng buộc Phase 1 vẫn áp dụng (Python ≥3.12, naive UTC, không gọi mạng trong pytest, retry 3 lần backoff 1/2/4s, API key không bao giờ trả về frontend, UI tiếng Việt, ghi rõ proxy).
- **Chỉ dữ liệu Mỹ:** Etsy chỉ giữ listing có `shop.is_shop_us_based == true` **và** `price.currency_code == "USD"`; Google Autocomplete gọi với `client=firefox&hl=en&gl=us`; Daily Trends gọi `https://trends.google.com/trending/rss?geo=US`.
- Etsy `SEARCH_LIMIT = 100`.
- Tag discovery: chỉ tag xuất hiện ở **≥ 3** listing (shop US) của cùng seed (`MIN_TAG_COUNT = 3`), tối đa 30 tag / seed.
- Chấm điểm: trọng số mặc định demand 0.35 / momentum 0.45 / competition 0.20 (đọc từ `backend/config/scoring.yaml`); cửa sổ active 7 ngày, lịch sử 30 ngày, nguồn "rising" khi growth > 0.2, thưởng hội tụ 0.1.
- Thứ tự ưu tiên metric velocity: `reviews` > `views` > `favorites`.
- Mỗi commit kết thúc bằng dòng: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`

## File Structure

```
backend/
  pyproject.toml                      # + pyyaml
  config/pod_filter.yaml              # NEW
  config/scoring.yaml                 # NEW
  app/config_files.py                 # NEW: load_yaml(name)
  app/models.py                       # + ProductSnapshot.views, Product.shop_sold_count, KeywordRelation, KeywordScore
  alembic/versions/<rev>_phase2.py    # NEW (autogenerate)
  app/keywords.py                     # get_or_create_keyword(..., has_parent=False) sets is_pod_relevant
  app/analysis/pod_filter.py          # NEW
  app/analysis/velocity.py            # views metric, velocity_metric()
  app/analysis/scoring.py             # NEW (pure)
  app/connectors/base.py              # NormalizedProduct.views/shop_sold_count, NormalizedSignal.parent
  app/connectors/etsy.py              # US filter, limit 100, keyword signals, tags
  app/connectors/google_suggest.py    # NEW
  app/connectors/google_daily.py      # NEW
  app/connectors/registry.py          # + 2 connectors
  app/pipeline/store.py               # relations, views, shop_sold_count
  app/pipeline/rescore.py             # NEW
  app/pipeline/scan.py                # call rescore after connectors
  app/api/schemas.py                  # ProductOut fields, Trend* schemas
  app/api/products.py                 # views, shop_sold_count, velocity_metric, popularity sort
  app/api/seeds.py                    # followed keyword → is_pod_relevant True
  app/api/trends.py                   # NEW
  app/main.py                         # include trends router
  scripts/rescore.py                  # NEW
  tests/fixtures/etsy/payload_nurse_shirt.json      # REWRITE
  tests/fixtures/google_suggest/nurse_shirt.json    # NEW
  tests/fixtures/google_daily/trending_us.xml       # NEW
  tests/test_pod_filter.py, test_google_suggest.py, test_google_daily.py,
  tests/test_scoring.py, test_rescore.py, test_api_trends.py   # NEW
Makefile                              # + rescore
frontend/
  lib/api.ts, lib/format.ts           # trend types/functions, labels
  components/Sparkline.tsx            # NEW
  components/ProductCard.tsx          # views + shop sold
  app/layout.tsx                      # nav + Trend Radar
  app/page.tsx                        # Trend Radar (replaces redirect)
  app/trends/[id]/page.tsx            # NEW keyword detail
  app/products/page.tsx               # sort label
README.md
```

---

### Task 1: Schema for Phase 2

**Files:**
- Modify: `backend/app/models.py`
- Create: `backend/alembic/versions/<rev>_phase2_trend_radar.py` (autogenerate)
- Test: `backend/tests/test_models.py` (append)

**Interfaces:**
- Produces: `ProductSnapshot.views: int | None`, `Product.shop_sold_count: int | None`, `KeywordRelation(parent_id, child_id, source, last_seen)` (composite PK parent_id+child_id+source), `KeywordScore(id, keyword_id, date, score, demand, momentum, competition, growth, sources_rising, sources)` (unique keyword_id+date; `sources` JSON list of str).

- [ ] **Step 1: Append failing tests to `backend/tests/test_models.py`**

```python
from app.models import KeywordRelation, KeywordScore


def test_snapshot_views_and_shop_sold_count(session):
    p = Product(source="etsy", external_id="9", title="T", url="u", product_type="tshirt", shop_sold_count=1500)
    session.add(p)
    session.flush()
    session.add(ProductSnapshot(product_id=p.id, date=date(2026, 10, 5), views=321))
    session.commit()
    session.refresh(p)
    assert p.shop_sold_count == 1500
    assert p.snapshots[0].views == 321


def test_keyword_relation_and_score(session):
    parent = get_or_create_keyword(session, "nurse")
    child = get_or_create_keyword(session, "nurse gift", origin="discovered")
    session.add(KeywordRelation(parent_id=parent.id, child_id=child.id, source="etsy_tags", last_seen=date(2026, 10, 5)))
    session.add(
        KeywordScore(
            keyword_id=child.id, date=date(2026, 10, 5), score=71.5, demand=0.8, momentum=None,
            competition=None, growth=None, sources_rising=0, sources=["etsy_tags"],
        )
    )
    session.commit()
    score = session.scalar(select(KeywordScore))
    assert (score.score, score.sources, score.momentum) == (71.5, ["etsy_tags"], None)
    assert session.get(KeywordRelation, (parent.id, child.id, "etsy_tags")) is not None


def test_keyword_score_unique_per_day(session):
    kw = get_or_create_keyword(session, "nurse")
    for _ in range(2):
        session.add(KeywordScore(keyword_id=kw.id, date=date(2026, 10, 5), score=1.0, sources_rising=0, sources=[]))
    with pytest.raises(IntegrityError):
        session.commit()
```

Also add `from sqlalchemy import select` to the file's imports if missing.

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && .venv/bin/pytest tests/test_models.py -v`
Expected: ImportError — `cannot import name 'KeywordRelation'`

- [ ] **Step 3: Edit `backend/app/models.py`**

In `Product`, after `listed_at`, add:

```python
    shop_sold_count: Mapped[int | None] = mapped_column(Integer)
```

In `ProductSnapshot`, after `bsr`, add:

```python
    views: Mapped[int | None] = mapped_column(Integer)
```

Append at end of file:

```python
class KeywordRelation(Base):
    """parent (seed) → child (niche discovered from tags/suggestions)."""

    __tablename__ = "keyword_relations"

    parent_id: Mapped[int] = mapped_column(ForeignKey("keywords.id"), primary_key=True)
    child_id: Mapped[int] = mapped_column(ForeignKey("keywords.id"), primary_key=True)
    source: Mapped[str] = mapped_column(String(30), primary_key=True)
    last_seen: Mapped[date] = mapped_column(Date)


class KeywordScore(Base):
    __tablename__ = "keyword_scores"
    __table_args__ = (UniqueConstraint("keyword_id", "date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    keyword_id: Mapped[int] = mapped_column(ForeignKey("keywords.id"))
    score: Mapped[float] = mapped_column(Float)
    demand: Mapped[float | None] = mapped_column(Float)
    momentum: Mapped[float | None] = mapped_column(Float)
    competition: Mapped[float | None] = mapped_column(Float)
    growth: Mapped[float | None] = mapped_column(Float)
    sources_rising: Mapped[int] = mapped_column(Integer, default=0)
    sources: Mapped[Any] = mapped_column(JSON, default=list)
    date: Mapped[date] = mapped_column(Date)
```

- [ ] **Step 4: Run model tests**

Run: `cd backend && .venv/bin/pytest tests/test_models.py -v` → all pass.

- [ ] **Step 5: Generate migration**

Run (from `backend/`): `.venv/bin/alembic upgrade head && .venv/bin/alembic revision --autogenerate -m "phase2 trend radar"`
Expected: new file in `alembic/versions/` containing `create_table('keyword_relations'`, `create_table('keyword_scores'`, and `batch_alter_table` add_column for `products.shop_sold_count` and `product_snapshots.views`. Open it and confirm; remove any unrelated operations if autogenerate added noise.
Then: `.venv/bin/alembic upgrade head` → succeeds.

- [ ] **Step 6: Run full suite** — `cd backend && .venv/bin/pytest -q` → all pass (test_migrations included).

- [ ] **Step 7: Commit**

```bash
git add backend/app/models.py backend/alembic/versions backend/tests/test_models.py
git commit -m "feat(backend): add phase 2 schema (views, shop sales, keyword relations, scores)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: POD relevance filter

**Files:**
- Modify: `backend/pyproject.toml` (add `"pyyaml>=6"` to `dependencies`)
- Create: `backend/config/pod_filter.yaml`, `backend/app/config_files.py`, `backend/app/analysis/pod_filter.py`
- Test: `backend/tests/test_pod_filter.py`

**Interfaces:**
- Produces: `load_yaml(name: str) -> dict` (cached, reads `backend/config/<name>`); `PodFilterRules(blocklist: tuple[str, ...], allow: frozenset[str])`; `load_rules() -> PodFilterRules` (cached); `is_pod_relevant(text: str, *, origin: str, has_parent: bool, rules: PodFilterRules | None = None) -> bool`.

Rule: origin `"seed"` → True. Else if any blocklist term appears as a whole word/phrase (regex `\b<term>\b`) → False. Else if `has_parent` → True. Else True iff any token (or token with trailing `s` removed) is in `allow`.

- [ ] **Step 1: Add dependency and install**

Add `"pyyaml>=6",` to `dependencies` in `backend/pyproject.toml`, then run `uv pip install --python backend/.venv/bin/python -e "backend[dev]"` (from repo root).

- [ ] **Step 2: Create `backend/config/pod_filter.yaml`**

```yaml
# Lọc keyword cho POD áo (t-shirt / sweatshirt / hoodie) — chỉnh tự do.
# blocklist: cụm từ cho thấy không phải nhu cầu mua áo thiết kế (so khớp nguyên từ).
blocklist:
  - near me
  - amazon
  - walmart
  - target
  - shein
  - temu
  - svg
  - png
  - pdf
  - free
  - template
  - clipart
  - cricut
  - mockup
  - wholesale
  - bulk
  - cheap
  - score
  - stats
  - lineup
  - schedule
  - tickets
  - weather
  - stock
  - death
  - died
  - arrested
  - lawsuit
# allow: từ đơn cho thấy ngách POD (dùng cho keyword không có parent, vd Daily Trends).
allow:
  apparel: [shirt, tee, tshirt, hoodie, sweatshirt, crewneck, apparel, gift, merch]
  family: [mom, mama, mommy, dad, daddy, papa, grandma, grandpa, nana, gigi, aunt, auntie, uncle, wife, husband, sister, brother, family, bride, groom]
  jobs: [nurse, teacher, doctor, nurse, rn, cna, paramedic, firefighter, police, trucker, mechanic, engineer, lawyer, chef, barber, hairstylist, pharmacist, dentist, vet, coach]
  pets: [dog, cat, puppy, kitten, horse, chicken, pet, corgi, dachshund, pitbull, golden]
  hobbies: [fishing, hunting, camping, hiking, golf, pickleball, tennis, baseball, softball, football, basketball, soccer, hockey, volleyball, bowling, gaming, gamer, reading, book, coffee, beer, wine, garden, gardening, yoga, running, cycling, farm, farmer, cowboy, cowgirl]
  occasions: [christmas, halloween, thanksgiving, valentine, easter, birthday, anniversary, wedding, graduation, retirement, mothers, fathers, patriotic, fourth, july, independence, veterans, memorial, st, patrick, patricks, oktoberfest, fall, autumn, spooky, summer, spring, winter]
```

- [ ] **Step 3: Write the failing test `backend/tests/test_pod_filter.py`**

```python
import pytest

from app.analysis.pod_filter import PodFilterRules, is_pod_relevant, load_rules


def test_rules_load_from_yaml():
    rules = load_rules()
    assert "near me" in rules.blocklist
    assert "nurse" in rules.allow
    assert "halloween" in rules.allow


@pytest.mark.parametrize(
    "text,origin,has_parent,expected",
    [
        ("nurse shirts near me", "seed", False, True),  # seeds always relevant
        ("nurse shirts near me", "discovered", True, False),
        ("nurse shirt svg", "discovered", True, False),
        ("funny nurse shirts", "discovered", True, True),
        ("halloween costume ideas", "discovered", False, True),
        ("braves dodgers game", "discovered", False, False),
        ("dog moms", "discovered", False, True),  # plural stripped
        ("freedom eagle shirt", "discovered", False, True),  # "free" must not match "freedom"
        ("chiefs score tonight", "discovered", False, False),
    ],
)
def test_is_pod_relevant(text, origin, has_parent, expected):
    assert is_pod_relevant(text, origin=origin, has_parent=has_parent) is expected


def test_custom_rules():
    rules = PodFilterRules(blocklist=("bad",), allow=frozenset({"good"}))
    assert is_pod_relevant("good thing", origin="discovered", has_parent=False, rules=rules) is True
    assert is_pod_relevant("good bad", origin="discovered", has_parent=False, rules=rules) is False
```

- [ ] **Step 4: Run to verify failure**

Run: `cd backend && .venv/bin/pytest tests/test_pod_filter.py -v`
Expected: ERROR — `No module named 'app.analysis.pod_filter'`

- [ ] **Step 5: Create `backend/app/config_files.py`**

```python
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"


@lru_cache
def load_yaml(name: str) -> dict[str, Any]:
    """Read backend/config/<name>; missing or empty file → {}."""
    path = CONFIG_DIR / name
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
```

- [ ] **Step 6: Create `backend/app/analysis/pod_filter.py`**

```python
import re
from dataclasses import dataclass
from functools import lru_cache

from app.config_files import load_yaml

_TOKEN = re.compile(r"[a-z0-9']+")


@dataclass(frozen=True)
class PodFilterRules:
    blocklist: tuple[str, ...]
    allow: frozenset[str]


@lru_cache
def load_rules() -> PodFilterRules:
    data = load_yaml("pod_filter.yaml")
    blocklist = tuple(" ".join(str(t).lower().split()) for t in data.get("blocklist", []))
    allow = frozenset(
        str(word).lower() for group in (data.get("allow") or {}).values() for word in group
    )
    return PodFilterRules(blocklist=blocklist, allow=allow)


def is_pod_relevant(
    text: str, *, origin: str, has_parent: bool, rules: PodFilterRules | None = None
) -> bool:
    if origin == "seed":
        return True
    rules = rules or load_rules()
    normalized = " ".join(text.lower().split())
    for term in rules.blocklist:
        if re.search(rf"\b{re.escape(term)}\b", normalized):
            return False
    if has_parent:
        return True
    tokens = set(_TOKEN.findall(normalized))
    tokens |= {t[:-1] for t in tokens if t.endswith("s") and len(t) > 3}
    return bool(tokens & rules.allow)
```

- [ ] **Step 7: Run tests** — `cd backend && .venv/bin/pytest tests/test_pod_filter.py -v` → 11 passed; then full suite.

- [ ] **Step 8: Commit**

```bash
git add backend/pyproject.toml backend/config/pod_filter.yaml backend/app/config_files.py backend/app/analysis/pod_filter.py backend/tests/test_pod_filter.py
git commit -m "feat(analysis): add YAML-configured POD relevance filter" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Contracts + store for relations, views, shop sales

**Files:**
- Modify: `backend/app/connectors/base.py`, `backend/app/keywords.py`, `backend/app/pipeline/store.py`, `backend/app/api/seeds.py`
- Test: `backend/tests/test_store.py` (append), `backend/tests/test_api_seeds_settings.py` (append)

**Interfaces:**
- Consumes: `is_pod_relevant` (Task 2), `KeywordRelation`, new columns (Task 1)
- Produces:
  - `NormalizedProduct` gains `views: int | None = None`, `shop_sold_count: int | None = None` (append after `bsr`).
  - `NormalizedSignal` gains `parent: str | None = None` (append after `origin`).
  - `get_or_create_keyword(session, text, origin="seed", *, has_parent=False) -> Keyword` — on **create** sets `is_pod_relevant = is_pod_relevant(norm, origin=origin, has_parent=has_parent)`; existing keywords unchanged.
  - `persist_batch` additionally: skips signals whose normalized keyword is empty; if `signal.parent` set → get_or_create parent (origin "seed") and upsert `KeywordRelation(parent_id, child_id, source=signal.source, last_seen=signal.date)` (skip when parent == child); stores `product.shop_sold_count` and `snapshot.views`.
  - `POST /api/seeds` sets the keyword's `is_pod_relevant = True`.

- [ ] **Step 1: Append failing tests to `backend/tests/test_store.py`**

```python
from app.models import KeywordRelation


def test_discovered_signal_creates_child_keyword_and_relation(session):
    sig = NormalizedSignal(
        keyword="Funny Nurse Shirts", source="google_suggest", metric="suggest_score",
        value=9.0, date=D1, origin="discovered", parent="nurse",
    )
    persist_batch(session, NormalizedBatch(signals=[sig]), D1)
    session.commit()

    child = session.scalar(select(Keyword).where(Keyword.text == "funny nurse shirts"))
    parent = session.scalar(select(Keyword).where(Keyword.text == "nurse"))
    assert (child.origin, child.is_pod_relevant) == ("discovered", True)
    assert parent.origin == "seed"
    rel = session.get(KeywordRelation, (parent.id, child.id, "google_suggest"))
    assert rel.last_seen == D1


def test_discovered_keywords_get_pod_relevance(session):
    signals = [
        NormalizedSignal(keyword="nurse shirts near me", source="google_suggest", metric="suggest_score", value=5.0, date=D1, origin="discovered", parent="nurse"),
        NormalizedSignal(keyword="braves dodgers game", source="google_daily", metric="traffic", value=200.0, date=D1, origin="discovered"),
        NormalizedSignal(keyword="halloween costume ideas", source="google_daily", metric="traffic", value=50000.0, date=D1, origin="discovered"),
        NormalizedSignal(keyword="   ", source="google_daily", metric="traffic", value=1.0, date=D1, origin="discovered"),
    ]
    persist_batch(session, NormalizedBatch(signals=signals), D1)
    session.commit()

    relevance = {k.text: k.is_pod_relevant for k in session.scalars(select(Keyword))}
    assert relevance["nurse shirts near me"] is False
    assert relevance["braves dodgers game"] is False
    assert relevance["halloween costume ideas"] is True
    assert "" not in relevance


def test_persists_views_and_shop_sold_count(session):
    persist_batch(session, NormalizedBatch(products=[make_product(views=420, shop_sold_count=9000)]), D1)
    session.commit()
    assert session.scalar(select(Product)).shop_sold_count == 9000
    assert session.scalar(select(ProductSnapshot)).views == 420
```

(`Keyword`, `Product`, `ProductSnapshot`, `NormalizedSignal`, `select` are already imported in that file; add any that are missing.)

- [ ] **Step 2: Append failing test to `backend/tests/test_api_seeds_settings.py`**

```python
def test_following_discovered_keyword_marks_it_relevant(client, session):
    from app.keywords import get_or_create_keyword
    from app.models import Keyword

    kw = get_or_create_keyword(session, "braves dodgers game", origin="discovered")
    session.commit()
    assert kw.is_pod_relevant is False

    resp = client.post("/api/seeds", json={"keyword": "braves dodgers game"})
    assert resp.status_code == 201
    session.expire_all()
    assert session.get(Keyword, kw.id).is_pod_relevant is True
```

- [ ] **Step 3: Run to verify failures**

Run: `cd backend && .venv/bin/pytest tests/test_store.py tests/test_api_seeds_settings.py -v`
Expected: failures (TypeError unexpected keyword `parent` / `views`; relevance assertion).

- [ ] **Step 4: Edit `backend/app/connectors/base.py`**

In `NormalizedProduct` after `bsr: int | None = None` add:

```python
    views: int | None = None
    shop_sold_count: int | None = None
```

In `NormalizedSignal` after `origin: str = "seed"` add:

```python
    parent: str | None = None  # seed keyword this niche was discovered from
```

- [ ] **Step 5: Replace `backend/app/keywords.py`**

```python
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.pod_filter import is_pod_relevant
from app.models import Keyword


def normalize_keyword(text: str) -> str:
    return " ".join(text.lower().split())


def get_or_create_keyword(
    session: Session, text: str, origin: str = "seed", *, has_parent: bool = False
) -> Keyword:
    norm = normalize_keyword(text)
    keyword = session.scalar(select(Keyword).where(Keyword.text == norm))
    if keyword is None:
        keyword = Keyword(
            text=norm,
            origin=origin,
            is_pod_relevant=is_pod_relevant(norm, origin=origin, has_parent=has_parent),
        )
        session.add(keyword)
        session.flush()
    return keyword
```

- [ ] **Step 6: Edit `backend/app/pipeline/store.py`**

Change the imports to:

```python
from app.connectors.base import NormalizedBatch, NormalizedProduct, NormalizedSignal
from app.keywords import get_or_create_keyword, normalize_keyword
from app.models import KeywordRelation, Product, ProductKeyword, ProductSnapshot, TrendSignal
```

Replace the start of `_upsert_signal` (the `keyword = get_or_create_keyword(...)` line) with:

```python
    if not normalize_keyword(signal.keyword):
        return
    keyword = get_or_create_keyword(
        session, signal.keyword, signal.origin, has_parent=signal.parent is not None
    )
    if signal.parent:
        _upsert_relation(session, signal.parent, keyword.id, signal.source, signal.date)
```

Add this function after `_upsert_signal`:

```python
def _upsert_relation(
    session: Session, parent_text: str, child_id: int, source: str, seen: date
) -> None:
    parent = get_or_create_keyword(session, parent_text)
    if parent.id == child_id:
        return
    relation = session.get(KeywordRelation, (parent.id, child_id, source))
    if relation is None:
        session.add(
            KeywordRelation(parent_id=parent.id, child_id=child_id, source=source, last_seen=seen)
        )
    else:
        relation.last_seen = seen
    session.flush()
```

In `_upsert_product`, after `product.listed_at = item.listed_at` add `product.shop_sold_count = item.shop_sold_count`; after `snapshot.bsr = item.bsr` add `snapshot.views = item.views`.

- [ ] **Step 7: Edit `backend/app/api/seeds.py` `create_seed`** — after `out = _to_out(session, seed)` and before `session.commit()`, add:

```python
    get_or_create_keyword(session, seed.keyword).is_pod_relevant = True  # user chose to follow it
```

- [ ] **Step 8: Run full suite** — `cd backend && .venv/bin/pytest -q` → all pass.

- [ ] **Step 9: Commit**

```bash
git add backend/app/connectors/base.py backend/app/keywords.py backend/app/pipeline/store.py backend/app/api/seeds.py backend/tests
git commit -m "feat(pipeline): persist keyword relations, POD relevance, views and shop sales" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Views-aware velocity + products API fields

**Files:**
- Modify: `backend/app/analysis/velocity.py`, `backend/app/api/schemas.py`, `backend/app/api/products.py`
- Test: `backend/tests/test_velocity.py` (append), `backend/tests/test_api_products.py` (append)

**Interfaces:**
- Produces:
  - `SnapshotPoint(date, reviews, favorites, views=None)` (new last field with default).
  - `METRIC_PRIORITY = ("reviews", "views", "favorites")`; `velocity_metric(snapshots) -> str | None` = highest-priority non-None metric of the latest snapshot that has any metric.
  - `compute_velocity` uses `velocity_metric` (behaviour otherwise unchanged).
  - `ProductOut` gains `views: int | None`, `shop_sold_count: int | None`, `velocity_metric: str | None` (append after `rating`, `keywords` stays last).
  - Sort `reviews` ("popularity") key: reviews, else views, else favorites.

- [ ] **Step 1: Append failing tests to `backend/tests/test_velocity.py`**

```python
from app.analysis.velocity import velocity_metric


def test_views_preferred_over_favorites():
    points = [
        SnapshotPoint(date(2026, 9, 20), reviews=None, favorites=5, views=100),
        SnapshotPoint(date(2026, 9, 27), reviews=None, favorites=6, views=240),
    ]
    assert velocity_metric(points) == "views"
    delta, _ = compute_velocity(points, None)
    assert delta == pytest.approx(140)


def test_velocity_metric_none_without_data():
    assert velocity_metric([SnapshotPoint(date(2026, 9, 27), None, None)]) is None
```

- [ ] **Step 2: Append failing test to `backend/tests/test_api_products.py`**

```python
def test_views_shop_sales_and_metric_exposed(client, session):
    from app.models import Product, ProductSnapshot

    p = Product(source="etsy", external_id="V", title="Views", url="u", product_type="tshirt",
                shop_sold_count=777, listed_at=datetime(2026, 9, 1))
    session.add(p)
    session.flush()
    session.add_all([
        ProductSnapshot(product_id=p.id, date=date(2026, 9, 20), favorites=1, views=100),
        ProductSnapshot(product_id=p.id, date=date(2026, 9, 27), favorites=2, views=300),
    ])
    session.commit()

    [item] = client.get("/api/products").json()["items"]
    assert (item["views"], item["shop_sold_count"], item["velocity_metric"]) == (300, 777, "views")
    assert item["delta_7d"] == pytest.approx(200)
```

- [ ] **Step 3: Run to verify failure** — `cd backend && .venv/bin/pytest tests/test_velocity.py tests/test_api_products.py -v` → ImportError / KeyError.

- [ ] **Step 4: Replace the top part of `backend/app/analysis/velocity.py`** (everything from `@dataclass(frozen=True) class SnapshotPoint` through the end of `compute_velocity`) with:

```python
METRIC_PRIORITY = ("reviews", "views", "favorites")


@dataclass(frozen=True)
class SnapshotPoint:
    date: date
    reviews: int | None
    favorites: int | None
    views: int | None = None


def velocity_metric(snapshots: list[SnapshotPoint]) -> str | None:
    """Metric for the whole series: best available one on the latest snapshot that has any."""
    for point in sorted(snapshots, key=lambda p: p.date, reverse=True):
        for name in METRIC_PRIORITY:
            if getattr(point, name) is not None:
                return name
    return None


def compute_velocity(
    snapshots: list[SnapshotPoint], listed_on: date | None
) -> tuple[float | None, float | None]:
    """Return (delta over 7 days, delta per week of listing age) for one metric series."""
    metric = velocity_metric(snapshots)
    if metric is None:
        return None, None
    points = sorted((p for p in snapshots if getattr(p, metric) is not None), key=lambda p: p.date)
    if len(points) < 2:
        return None, None
    latest = points[-1]
    cutoff = latest.date - timedelta(days=WINDOW_DAYS)
    older = [p for p in points[:-1] if p.date <= cutoff]
    base = older[-1] if older else points[0]
    span = (latest.date - base.date).days
    if span < MIN_SPAN_DAYS:
        return None, None
    delta_7d = (getattr(latest, metric) - getattr(base, metric)) * WINDOW_DAYS / span
    weeks = (latest.date - listed_on).days / 7 if listed_on else 1.0
    return delta_7d, delta_7d / max(1.0, weeks)
```

(Delete the old `_chosen_metric_name` helper. Keep `hot_ids` unchanged.)

- [ ] **Step 5: Edit `backend/app/api/schemas.py` `ProductOut`** — after `rating: float | None` add:

```python
    views: int | None
    shop_sold_count: int | None
    velocity_metric: str | None
```

- [ ] **Step 6: Edit `backend/app/api/products.py`**
  - Import: `from app.analysis.velocity import SnapshotPoint, compute_velocity, hot_ids, velocity_metric`.
  - Replace the `"reviews"` entry in `SORTS` with:

```python
    "reviews": lambda p: _desc_none_last(
        next((v for v in (p.reviews, p.views, p.favorites) if v is not None), None)
    ),
```

  - Build points once per product including views. Replace the `metrics = {...}` block with:

```python
    points = {
        p.id: [SnapshotPoint(s.date, s.reviews, s.favorites, s.views) for s in p.snapshots]
        for p in products
    }
    metrics = {
        p.id: compute_velocity(points[p.id], p.listed_at.date() if p.listed_at else None)
        for p in products
    }
```

  - Pass the metric name into `_to_out`: change the list comprehension call to `_to_out(p, metrics[p.id], velocity_metric(points[p.id]), p.id in hot, sorted(keyword_texts[p.id]))` and the signature to `def _to_out(p, metric, metric_name: str | None, hot, keywords)`; in the `ProductOut(...)` add:

```python
        views=latest.views if latest else None,
        shop_sold_count=p.shop_sold_count,
        velocity_metric=metric_name,
```

  - While here, wrap the overlong `products = session.scalars(...)` line over multiple lines (≤ 100 chars).

- [ ] **Step 7: Run full suite** — all pass.

- [ ] **Step 8: Commit**

```bash
git add backend/app/analysis/velocity.py backend/app/api backend/tests
git commit -m "feat(analysis): prefer views for velocity and expose views/shop sales" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Etsy connector — US only, keyword signals, tag discovery

**Files:**
- Modify: `backend/app/connectors/etsy.py`
- Rewrite: `backend/tests/fixtures/etsy/payload_nurse_shirt.json`
- Modify: `backend/tests/test_etsy.py`

**Interfaces:**
- Consumes: `NormalizedSignal.parent`, `NormalizedProduct.views/shop_sold_count` (Task 3), `normalize_keyword` (keywords.py)
- Produces: constants `SEARCH_LIMIT = 100`, `MIN_TAG_COUNT = 3`, `MAX_TAGS_PER_SEED = 30`, `NEW_LISTING_DAYS = 30`. `normalize` emits:
  - products only for apparel listings whose `shop.is_shop_us_based is True` and currency `"USD"` (views, shop_sold_count = `shop.transaction_sold_count`);
  - per payload: `etsy/listing_count_<type>` (unchanged);
  - per seed keyword (deduped by listing_id across its payloads, US apparel only): `etsy/us_listing_count`, `etsy/views_per_day` (mean of `views / max(1, age_days)` over listings with views and a creation time; omitted if none), `etsy/new_listings_30d`;
  - tag signals: `NormalizedSignal(keyword=<tag>, source="etsy_tags", metric="tag_count", value=<n>, date=today, origin="discovered", parent=<seed>)` for tags (normalized, HTML-unescaped, counted once per listing) with n ≥ 3, excluding the seed itself, top 30 by count.

- [ ] **Step 1: Rewrite `backend/tests/fixtures/etsy/payload_nurse_shirt.json`**

```json
{
  "keyword": "nurse",
  "query": "nurse shirt",
  "product_type": "tshirt",
  "search": {
    "count": 12345,
    "results": [
      {"listing_id": 1001, "title": "Funny Nurse Shirt &amp; Gift", "price": {"amount": 2499, "divisor": 100, "currency_code": "USD"}, "num_favorers": 532, "views": 1200, "tags": ["nurse shirt", "Nurse Gift", "funny nurse", "rn shirt"], "url": "https://www.etsy.com/listing/1001/funny-nurse-shirt", "creation_timestamp": 1756684800, "original_creation_timestamp": 1754006400, "shop_id": 11},
      {"listing_id": 1002, "title": "Nurse Coffee Mug", "price": {"amount": 1599, "divisor": 100, "currency_code": "USD"}, "num_favorers": 40, "views": 50, "tags": ["nurse gift", "rn shirt", "nurse mug"], "url": "https://www.etsy.com/listing/1002/nurse-mug", "creation_timestamp": 1756684800, "shop_id": 11},
      {"listing_id": 1003, "title": "Retro Nurse Hoodie, Nurse Life Sweatshirt", "price": {"amount": 3999, "divisor": 100, "currency_code": "USD"}, "num_favorers": 87, "views": 300, "tags": ["nurse hoodie", "nurse gift", "retro nurse", "rn shirt"], "url": "https://www.etsy.com/listing/1003/retro-nurse-hoodie", "creation_timestamp": 1789862400, "shop_id": 12},
      {"listing_id": 1004, "title": "Nurse Shirt Vintage", "price": {"amount": 1500, "divisor": 100, "currency_code": "USD"}, "num_favorers": 10, "views": 90, "tags": ["nurse gift", "rn shirt", "vintage nurse"], "url": "https://www.etsy.com/listing/1004/nurse-shirt-vintage", "creation_timestamp": 1789862400, "shop_id": 13},
      {"listing_id": 1005, "title": "Nurse Week Tee", "price": {"amount": 2200, "divisor": 100, "currency_code": "CAD"}, "num_favorers": 3, "views": 20, "tags": ["nurse gift", "rn shirt"], "url": "https://www.etsy.com/listing/1005/nurse-week-tee", "creation_timestamp": 1789862400, "shop_id": 11},
      {"listing_id": 1006, "title": "Nurse Crewneck Sweatshirt", "price": {"amount": 3200, "divisor": 100, "currency_code": "USD"}, "num_favorers": 5, "views": 60, "tags": ["nurse gift", "RN shirt", "nurse crewneck", "nurse"], "url": "https://www.etsy.com/listing/1006/nurse-crewneck", "creation_timestamp": 1789862400, "shop_id": 12}
    ]
  },
  "details": {
    "count": 6,
    "results": [
      {"listing_id": 1001, "images": [{"url_570xN": "https://i.etsystatic.com/1001_570xN.jpg"}], "shop": {"shop_id": 11, "shop_name": "NurseLifeCo", "is_shop_us_based": true, "transaction_sold_count": 15400}},
      {"listing_id": 1002, "images": [], "shop": {"shop_id": 11, "shop_name": "NurseLifeCo", "is_shop_us_based": true, "transaction_sold_count": 15400}},
      {"listing_id": 1003, "images": [], "shop": {"shop_id": 12, "shop_name": "RetroScrubs", "is_shop_us_based": true, "transaction_sold_count": 820}},
      {"listing_id": 1004, "images": [], "shop": {"shop_id": 13, "shop_name": "FarAwayTees", "is_shop_us_based": false, "transaction_sold_count": 3}},
      {"listing_id": 1005, "images": [], "shop": {"shop_id": 11, "shop_name": "NurseLifeCo", "is_shop_us_based": true, "transaction_sold_count": 15400}},
      {"listing_id": 1006, "images": [], "shop": {"shop_id": 12, "shop_name": "RetroScrubs", "is_shop_us_based": true, "transaction_sold_count": 820}}
    ]
  }
}
```

(Timestamps: 1754006400 = 2025-08-01, 1789862400 = 2026-09-20 UTC. With today = 2026-10-05: ages 430 and 15 days.)

- [ ] **Step 2: Update `backend/tests/test_etsy.py`**

Replace `test_normalize_maps_apparel_listings_and_drops_others` with:

```python
TODAY = date(2026, 10, 5)


def test_normalize_keeps_us_usd_apparel_only():
    raw = RawBatch(source="etsy", payloads=[load_payload()])
    batch = EtsyConnector("k").normalize(raw, TODAY)

    # 1002 mug (not apparel), 1004 non-US shop, 1005 CAD price are dropped
    assert [p.external_id for p in batch.products] == ["1001", "1003", "1006"]
    shirt, hoodie, crew = batch.products
    assert shirt.title == "Funny Nurse Shirt & Gift"
    assert shirt.price == 24.99
    assert shirt.currency == "USD"
    assert shirt.favorites == 532
    assert shirt.views == 1200
    assert shirt.shop_sold_count == 15400
    assert shirt.image_url == "https://i.etsystatic.com/1001_570xN.jpg"
    assert shirt.shop_name == "NurseLifeCo"
    assert shirt.product_type == "tshirt"
    assert shirt.listed_at == datetime(2025, 8, 1)
    assert (shirt.keyword, shirt.rank) == ("nurse", 1)
    assert (hoodie.product_type, hoodie.rank, hoodie.image_url) == ("hoodie", 3, None)
    assert (crew.product_type, crew.rank) == ("sweatshirt", 6)


def test_normalize_emits_keyword_signals_and_tags():
    raw = RawBatch(source="etsy", payloads=[load_payload()])
    signals = EtsyConnector("k").normalize(raw, TODAY).signals
    by_metric = {(s.source, s.metric, s.keyword): s for s in signals}

    assert by_metric[("etsy", "listing_count_tshirt", "nurse")].value == 12345.0
    assert by_metric[("etsy", "us_listing_count", "nurse")].value == 3.0
    assert by_metric[("etsy", "new_listings_30d", "nurse")].value == 2.0
    expected_rate = (1200 / 430 + 300 / 15 + 60 / 15) / 3
    assert by_metric[("etsy", "views_per_day", "nurse")].value == pytest.approx(expected_rate)

    tags = {s.keyword: s for s in signals if s.source == "etsy_tags"}
    assert set(tags) == {"nurse gift", "rn shirt"}  # only tags on >= 3 kept US listings
    gift = tags["nurse gift"]
    assert (gift.metric, gift.value, gift.origin, gift.parent, gift.date) == (
        "tag_count", 3.0, "discovered", "nurse", TODAY
    )
    assert all(s.date == TODAY for s in signals)


def test_keyword_signals_dedupe_listings_across_queries():
    payload = load_payload()
    second = {**payload, "query": "nurse hoodie", "product_type": "hoodie"}
    raw = RawBatch(source="etsy", payloads=[payload, second])
    signals = EtsyConnector("k").normalize(raw, TODAY).signals
    us_count = [s for s in signals if s.metric == "us_listing_count"]
    assert [s.value for s in us_count] == [3.0]
    assert {s.metric for s in signals if s.metric.startswith("listing_count_")} == {
        "listing_count_tshirt", "listing_count_hoodie"
    }
```

Add `import pytest` to the imports. In `test_fetch_runs_search_and_batch_per_product_type` change the listing_ids assertion to `"1001,1002,1003,1004,1005,1006"` and add `assert first.url.params["limit"] == "100"`.

Replace the payload in `test_normalize_skips_listings_without_id` so listing 7 is a US/USD listing:

```python
    payload = {
        "keyword": "nurse",
        "query": "nurse shirt",
        "product_type": "tshirt",
        "search": {
            "count": 2,
            "results": [
                {"title": "Broken Shirt"},
                {"listing_id": 7, "title": "Nurse Shirt", "price": {"amount": 2000, "divisor": 100, "currency_code": "USD"}},
            ],
        },
        "details": {"results": [{"title": "Broken Detail Shirt"}, {"listing_id": 7, "shop": {"is_shop_us_based": True}}]},
    }
```

- [ ] **Step 3: Run to verify failure** — `cd backend && .venv/bin/pytest tests/test_etsy.py -v` → failures.

- [ ] **Step 4: Edit `backend/app/connectors/etsy.py`**

Imports: add `from collections import Counter` and `from app.keywords import normalize_keyword`. Constants:

```python
SEARCH_LIMIT = 100
MIN_TAG_COUNT = 3  # a tag must appear on >= 3 US listings of the seed to become a niche
MAX_TAGS_PER_SEED = 30
NEW_LISTING_DAYS = 30
```

Replace `normalize` and `_to_product` with:

```python
    def normalize(self, raw: RawBatch, today: date) -> NormalizedBatch:
        batch = NormalizedBatch()
        kept: dict[str, dict[str, dict[str, Any]]] = {}  # seed -> listing_id -> listing
        for payload in raw.payloads:
            keyword = payload["keyword"]
            search = payload.get("search", {})
            if search.get("count") is not None:
                batch.signals.append(
                    NormalizedSignal(
                        keyword=keyword,
                        source=self.name,
                        metric=f"listing_count_{payload['product_type']}",
                        value=float(search["count"]),
                        date=today,
                    )
                )
            details = {
                str(d["listing_id"]): d
                for d in payload.get("details", {}).get("results", [])
                if "listing_id" in d
            }
            for rank, item in enumerate(search.get("results", []), start=1):
                if "listing_id" not in item:
                    continue
                listing = {**item, **details.get(str(item["listing_id"]), {})}
                product = _to_product(listing, keyword, rank)
                if product is not None:
                    batch.products.append(product)
                    kept.setdefault(keyword, {}).setdefault(product.external_id, listing)
        for keyword, listings in kept.items():
            batch.signals.extend(_keyword_signals(keyword, list(listings.values()), today))
        return batch


def _created_at(listing: dict[str, Any]) -> datetime | None:
    created = listing.get("original_creation_timestamp") or listing.get("creation_timestamp")
    return datetime.fromtimestamp(created, tz=timezone.utc).replace(tzinfo=None) if created else None


def _is_us_usd(listing: dict[str, Any]) -> bool:
    shop = listing.get("shop") or {}
    price = listing.get("price") or {}
    return shop.get("is_shop_us_based") is True and price.get("currency_code") == "USD"


def _to_product(listing: dict[str, Any], keyword: str, rank: int) -> NormalizedProduct | None:
    title = html.unescape(listing.get("title") or "").strip()
    product_type = classify_product_type(title)
    if product_type == "other" or not _is_us_usd(listing):
        return None
    price = listing.get("price") or {}
    amount = price.get("amount")
    divisor = price.get("divisor") or 1
    images = listing.get("images") or []
    shop = listing.get("shop") or {}
    listing_id = str(listing["listing_id"])
    return NormalizedProduct(
        source="etsy",
        external_id=listing_id,
        title=title,
        url=listing.get("url") or f"https://www.etsy.com/listing/{listing_id}",
        image_url=images[0].get("url_570xN") if images else None,
        shop_name=shop.get("shop_name"),
        price=amount / divisor if amount is not None else None,
        currency=price.get("currency_code"),
        product_type=product_type,
        listed_at=_created_at(listing),
        keyword=keyword,
        rank=rank,
        favorites=listing.get("num_favorers"),
        views=listing.get("views"),
        shop_sold_count=shop.get("transaction_sold_count"),
    )


def _keyword_signals(
    keyword: str, listings: list[dict[str, Any]], today: date
) -> list[NormalizedSignal]:
    def signal(metric: str, value: float) -> NormalizedSignal:
        return NormalizedSignal(keyword=keyword, source="etsy", metric=metric, value=value, date=today)

    rates: list[float] = []
    new_listings = 0
    for listing in listings:
        created = _created_at(listing)
        if created is None:
            continue
        age_days = max(1, (today - created.date()).days)
        if listing.get("views") is not None:
            rates.append(listing["views"] / age_days)
        if age_days <= NEW_LISTING_DAYS:
            new_listings += 1

    signals = [
        signal("us_listing_count", float(len(listings))),
        signal("new_listings_30d", float(new_listings)),
    ]
    if rates:
        signals.append(signal("views_per_day", sum(rates) / len(rates)))

    seed = normalize_keyword(keyword)
    tag_counts = Counter(
        tag
        for listing in listings
        for tag in {normalize_keyword(html.unescape(t)) for t in listing.get("tags") or []}
        if tag and tag != seed
    )
    for tag, count in tag_counts.most_common(MAX_TAGS_PER_SEED):
        if count < MIN_TAG_COUNT:
            break
        signals.append(
            NormalizedSignal(
                keyword=tag, source="etsy_tags", metric="tag_count", value=float(count),
                date=today, origin="discovered", parent=keyword,
            )
        )
    return signals
```

- [ ] **Step 5: Run tests** — `cd backend && .venv/bin/pytest tests/test_etsy.py -v`, then full suite → all pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/connectors/etsy.py backend/tests/test_etsy.py backend/tests/fixtures/etsy/payload_nurse_shirt.json
git commit -m "feat(connectors): Etsy US-only listings, keyword demand signals and tag discovery" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Google Autocomplete connector (US)

**Files:**
- Create: `backend/app/connectors/google_suggest.py`, `backend/tests/fixtures/google_suggest/nurse_shirt.json`
- Test: `backend/tests/test_google_suggest.py`

**Interfaces:**
- Consumes: `RawBatch`, `NormalizedBatch`, `NormalizedSignal`, `ConnectorError`, `RateLimiter`, `request_with_retry`, `normalize_keyword`
- Produces: `GoogleSuggestConnector(*, min_interval: float = 1.0, sleep=asyncio.sleep)`; `name = "google_suggest"`, `kind = "trend"`, `enabled()` always True. Raw payload: `{"keyword": seed, "query": "<seed> <suffix>", "suggestions": [str, ...]}`. Signals: per (seed, suggestion) best rank r (1-based, first 10) → `NormalizedSignal(keyword=<suggestion normalized>, source="google_suggest", metric="suggest_score", value=11 - r, date=today, origin="discovered", parent=seed)`; skip suggestions equal to the query itself or empty.
- Constants: `SUGGEST_URL = "https://suggestqueries.google.com/complete/search"`, `QUERY_SUFFIXES = ("shirt", "hoodie", "sweatshirt")`, `USER_AGENT` (desktop Chrome UA string).

- [ ] **Step 1: Create fixture `backend/tests/fixtures/google_suggest/nurse_shirt.json`** (captured live, US):

```json
["nurse shirt",["nurse shirts","nurse shirt designs","nurse shirts near me","nurse shirts for work","nurse shirts funny","nurse shirt ideas","nurse shirts for women","nurse shirts amazon","nurse shirt svg","nurse shirt png"],[],{"google:suggestsubtypes":[[512],[512],[512],[512],[512],[512],[512],[512],[512],[512]]}]
```

- [ ] **Step 2: Write the failing test `backend/tests/test_google_suggest.py`**

```python
import json
from datetime import date
from pathlib import Path

import httpx
import respx

from app.connectors.base import RawBatch
from app.connectors.google_suggest import SUGGEST_URL, GoogleSuggestConnector

FIXTURE = Path(__file__).parent / "fixtures" / "google_suggest" / "nurse_shirt.json"
TODAY = date(2026, 10, 5)


async def no_sleep(_seconds: float) -> None:
    return None


def suggestions() -> list[str]:
    return json.loads(FIXTURE.read_text())[1]


def test_always_enabled_trend_source():
    c = GoogleSuggestConnector()
    assert (c.name, c.kind, c.enabled()) == ("google_suggest", "trend", True)


def test_normalize_scores_suggestions_by_rank():
    raw = RawBatch(source="google_suggest", payloads=[
        {"keyword": "nurse", "query": "nurse shirt", "suggestions": suggestions()}
    ])
    signals = GoogleSuggestConnector().normalize(raw, TODAY).signals

    assert len(signals) == 10
    first = signals[0]
    assert (first.keyword, first.source, first.metric, first.value) == (
        "nurse shirts", "google_suggest", "suggest_score", 10.0
    )
    assert (first.origin, first.parent, first.date) == ("discovered", "nurse", TODAY)
    assert signals[-1].keyword == "nurse shirt png" and signals[-1].value == 1.0


def test_normalize_keeps_best_rank_and_skips_query_echo():
    raw = RawBatch(source="google_suggest", payloads=[
        {"keyword": "nurse", "query": "nurse shirt", "suggestions": ["nurse shirt", "a", "nurse gift"]},
        {"keyword": "nurse", "query": "nurse hoodie", "suggestions": ["nurse gift"]},
    ])
    signals = {s.keyword: s.value for s in GoogleSuggestConnector().normalize(raw, TODAY).signals}
    assert signals == {"a": 9.0, "nurse gift": 10.0}


@respx.mock
async def test_fetch_queries_us_suggestions_per_suffix():
    route = respx.get(url__startswith=SUGGEST_URL).mock(
        return_value=httpx.Response(200, content=FIXTURE.read_bytes(), headers={"content-type": "application/json"})
    )
    raw = await GoogleSuggestConnector(min_interval=0, sleep=no_sleep).fetch(["nurse"])

    assert [p["query"] for p in raw.payloads] == ["nurse shirt", "nurse hoodie", "nurse sweatshirt"]
    assert raw.payloads[0]["suggestions"][0] == "nurse shirts"
    assert raw.errors == []
    params = route.calls[0].request.url.params
    assert (params["client"], params["hl"], params["gl"], params["q"]) == ("firefox", "en", "us", "nurse shirt")


@respx.mock
async def test_fetch_collects_errors():
    respx.get(url__startswith=SUGGEST_URL).mock(return_value=httpx.Response(200, text="not json"))
    raw = await GoogleSuggestConnector(min_interval=0, sleep=no_sleep).fetch(["nurse"])
    assert raw.payloads == []
    assert len(raw.errors) == 3
```

- [ ] **Step 3: Run to verify failure** — ModuleNotFoundError.

- [ ] **Step 4: Create `backend/app/connectors/google_suggest.py`**

```python
"""Google Autocomplete (US): niche ideas people type after '<seed> shirt'."""

import asyncio
from datetime import date
from typing import Any

import httpx

from app.connectors.base import ConnectorError, NormalizedBatch, NormalizedSignal, RawBatch
from app.connectors.http import RateLimiter, Sleep, request_with_retry
from app.keywords import normalize_keyword

SUGGEST_URL = "https://suggestqueries.google.com/complete/search"
QUERY_SUFFIXES = ("shirt", "hoodie", "sweatshirt")
MAX_SUGGESTIONS = 10
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/129.0 Safari/537.36"
)


class GoogleSuggestConnector:
    name = "google_suggest"
    kind = "trend"

    def __init__(self, *, min_interval: float = 1.0, sleep: Sleep = asyncio.sleep) -> None:
        self._sleep = sleep
        self._limiter = RateLimiter(min_interval, sleep=sleep)

    def enabled(self) -> bool:
        return True

    async def fetch(self, keywords: list[str]) -> RawBatch:
        payloads: list[dict[str, Any]] = []
        errors: list[str] = []
        async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}, timeout=15.0) as client:
            for keyword in keywords:
                for suffix in QUERY_SUFFIXES:
                    query = f"{keyword} {suffix}"
                    try:
                        payloads.append(
                            {"keyword": keyword, "query": query, "suggestions": await self._suggest(client, query)}
                        )
                    except ConnectorError as exc:
                        errors.append(f"{query}: {exc}")
        return RawBatch(source=self.name, payloads=payloads, errors=errors)

    async def _suggest(self, client: httpx.AsyncClient, query: str) -> list[str]:
        response = await request_with_retry(
            client,
            "GET",
            SUGGEST_URL,
            params={"client": "firefox", "hl": "en", "gl": "us", "q": query},
            limiter=self._limiter,
            sleep=self._sleep,
        )
        try:
            data = response.json()
        except ValueError as exc:
            raise ConnectorError("invalid JSON from suggest") from exc
        if not isinstance(data, list) or len(data) < 2 or not isinstance(data[1], list):
            raise ConnectorError("unexpected suggest response shape")
        return [str(s) for s in data[1]]

    def normalize(self, raw: RawBatch, today: date) -> NormalizedBatch:
        best: dict[tuple[str, str], int] = {}
        for payload in raw.payloads:
            query = normalize_keyword(payload["query"])
            for rank, suggestion in enumerate(payload.get("suggestions", [])[:MAX_SUGGESTIONS], start=1):
                text = normalize_keyword(suggestion)
                if not text or text == query:
                    continue
                key = (payload["keyword"], text)
                best[key] = min(best.get(key, rank), rank)
        return NormalizedBatch(
            signals=[
                NormalizedSignal(
                    keyword=text, source=self.name, metric="suggest_score",
                    value=float(MAX_SUGGESTIONS + 1 - rank), date=today,
                    origin="discovered", parent=seed,
                )
                for (seed, text), rank in best.items()
            ]
        )
```

Note: in `test_normalize_keeps_best_rank_and_skips_query_echo`, "nurse shirt" is skipped (echo) but still occupies rank 1, so "a" is rank 2 → 9.0 and "nurse gift" best rank 1 (second payload) → 10.0.

- [ ] **Step 5: Run tests** → 5 passed; full suite passes.

- [ ] **Step 6: Commit**

```bash
git add backend/app/connectors/google_suggest.py backend/tests/test_google_suggest.py backend/tests/fixtures/google_suggest
git commit -m "feat(connectors): add US Google Autocomplete niche discovery" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Google Daily Trends (US) connector + registry

**Files:**
- Create: `backend/app/connectors/google_daily.py`, `backend/tests/fixtures/google_daily/trending_us.xml`
- Modify: `backend/app/connectors/registry.py`
- Test: `backend/tests/test_google_daily.py`; update `backend/tests/test_scan.py`, `backend/tests/test_api_seeds_settings.py`, `backend/tests/test_api_scans_health.py`

**Interfaces:**
- Produces: `GoogleDailyTrendsConnector(*, sleep=asyncio.sleep)`; `name = "google_daily"`, `kind = "trend"`, `enabled()` True. `fetch(keywords)` ignores keywords; one GET `RSS_URL` with `params={"geo": "US"}`; payload `{"geo": "US", "xml": <text>}`; errors collected. `normalize`: each `<item>` → `NormalizedSignal(keyword=<title>, source="google_daily", metric="traffic", value=parse_traffic(<ht:approx_traffic>), date=today, origin="discovered")`, skipping unparseable traffic/empty titles; malformed XML → that payload is skipped (logged). `parse_traffic("200+") == 200.0`, `"50K+" → 50000.0`, `"2M+" → 2000000.0`, `"1,000+" → 1000.0`, invalid → `None`.
- `make_all_connectors(settings)` returns `[EtsyConnector(...), GoogleSuggestConnector(), GoogleDailyTrendsConnector()]` (in that order).

- [ ] **Step 1: Create fixture `backend/tests/fixtures/google_daily/trending_us.xml`**

```xml
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<rss xmlns:atom="http://www.w3.org/2005/Atom" xmlns:ht="https://trends.google.com/trending/rss" version="2.0">
  <channel>
    <title>Daily Search Trends</title>
    <item>
      <title>braves dodgers game</title>
      <ht:approx_traffic>200+</ht:approx_traffic>
      <pubDate>Mon, 5 Oct 2026 02:10:00 -0700</pubDate>
    </item>
    <item>
      <title>Halloween Costume Ideas</title>
      <ht:approx_traffic>50K+</ht:approx_traffic>
      <pubDate>Mon, 5 Oct 2026 01:00:00 -0700</pubDate>
    </item>
    <item>
      <title>nurse appreciation week</title>
      <ht:approx_traffic>2M+</ht:approx_traffic>
      <pubDate>Mon, 5 Oct 2026 00:30:00 -0700</pubDate>
    </item>
    <item>
      <title>broken item</title>
      <ht:approx_traffic>lots</ht:approx_traffic>
    </item>
  </channel>
</rss>
```

- [ ] **Step 2: Write the failing test `backend/tests/test_google_daily.py`**

```python
from datetime import date
from pathlib import Path

import httpx
import pytest
import respx

from app.connectors.base import RawBatch
from app.connectors.google_daily import RSS_URL, GoogleDailyTrendsConnector, parse_traffic

FIXTURE = Path(__file__).parent / "fixtures" / "google_daily" / "trending_us.xml"
TODAY = date(2026, 10, 5)


async def no_sleep(_seconds: float) -> None:
    return None


@pytest.mark.parametrize(
    "text,expected",
    [("200+", 200.0), ("50K+", 50000.0), ("2M+", 2000000.0), ("1,000+", 1000.0), ("lots", None), ("", None)],
)
def test_parse_traffic(text, expected):
    assert parse_traffic(text) == expected


def test_normalize_items_to_traffic_signals():
    raw = RawBatch(source="google_daily", payloads=[{"geo": "US", "xml": FIXTURE.read_text()}])
    signals = GoogleDailyTrendsConnector().normalize(raw, TODAY).signals
    assert [(s.keyword, s.value) for s in signals] == [
        ("braves dodgers game", 200.0),
        ("Halloween Costume Ideas", 50000.0),
        ("nurse appreciation week", 2000000.0),
    ]
    assert all(
        (s.source, s.metric, s.origin, s.parent, s.date) == ("google_daily", "traffic", "discovered", None, TODAY)
        for s in signals
    )


def test_normalize_skips_malformed_xml():
    raw = RawBatch(source="google_daily", payloads=[{"geo": "US", "xml": "<rss><broken"}])
    assert GoogleDailyTrendsConnector().normalize(raw, TODAY).signals == []


@respx.mock
async def test_fetch_us_feed_once():
    route = respx.get(url__startswith=RSS_URL).mock(return_value=httpx.Response(200, text=FIXTURE.read_text()))
    raw = await GoogleDailyTrendsConnector(sleep=no_sleep).fetch(["nurse", "dog mom"])
    assert route.call_count == 1
    assert route.calls[0].request.url.params["geo"] == "US"
    assert raw.payloads[0]["geo"] == "US" and "braves" in raw.payloads[0]["xml"]
    assert raw.errors == []


@respx.mock
async def test_fetch_error_is_collected():
    respx.get(url__startswith=RSS_URL).mock(return_value=httpx.Response(404))
    raw = await GoogleDailyTrendsConnector(sleep=no_sleep).fetch([])
    assert raw.payloads == [] and len(raw.errors) == 1
```

- [ ] **Step 3: Run to verify failure** — ModuleNotFoundError.

- [ ] **Step 4: Create `backend/app/connectors/google_daily.py`**

```python
"""Google Daily Search Trends RSS for the US (hot events / searches)."""

import asyncio
import logging
import xml.etree.ElementTree as ET
from datetime import date

import httpx

from app.connectors.base import ConnectorError, NormalizedBatch, NormalizedSignal, RawBatch
from app.connectors.google_suggest import USER_AGENT
from app.connectors.http import Sleep, request_with_retry

logger = logging.getLogger(__name__)
RSS_URL = "https://trends.google.com/trending/rss"
HT_NS = "{https://trends.google.com/trending/rss}"
_MULTIPLIERS = {"K": 1_000.0, "M": 1_000_000.0}


def parse_traffic(text: str) -> float | None:
    cleaned = text.strip().rstrip("+").replace(",", "").upper()
    if not cleaned:
        return None
    multiplier = _MULTIPLIERS.get(cleaned[-1], 1.0)
    number = cleaned[:-1] if cleaned[-1] in _MULTIPLIERS else cleaned
    try:
        return float(number) * multiplier
    except ValueError:
        return None


class GoogleDailyTrendsConnector:
    name = "google_daily"
    kind = "trend"

    def __init__(self, *, sleep: Sleep = asyncio.sleep) -> None:
        self._sleep = sleep

    def enabled(self) -> bool:
        return True

    async def fetch(self, keywords: list[str]) -> RawBatch:
        """Seed keywords are not used: the daily feed is country-wide."""
        async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}, timeout=20.0) as client:
            try:
                response = await request_with_retry(
                    client, "GET", RSS_URL, params={"geo": "US"}, sleep=self._sleep
                )
            except ConnectorError as exc:
                return RawBatch(source=self.name, payloads=[], errors=[str(exc)])
        return RawBatch(source=self.name, payloads=[{"geo": "US", "xml": response.text}])

    def normalize(self, raw: RawBatch, today: date) -> NormalizedBatch:
        batch = NormalizedBatch()
        for payload in raw.payloads:
            try:
                root = ET.fromstring(payload["xml"])
            except ET.ParseError:
                logger.warning("Skipping malformed Daily Trends RSS payload")
                continue
            for item in root.iter("item"):
                title = (item.findtext("title") or "").strip()
                traffic = parse_traffic(item.findtext(f"{HT_NS}approx_traffic") or "")
                if not title or traffic is None:
                    continue
                batch.signals.append(
                    NormalizedSignal(
                        keyword=title, source=self.name, metric="traffic", value=traffic,
                        date=today, origin="discovered",
                    )
                )
        return batch
```

- [ ] **Step 5: Edit `backend/app/connectors/registry.py`** — import both new connectors and change `make_all_connectors` to:

```python
def make_all_connectors(settings: Settings) -> list[Connector]:
    return [
        EtsyConnector(api_key=settings.etsy_api_key),
        GoogleSuggestConnector(),
        GoogleDailyTrendsConnector(),
    ]
```

- [ ] **Step 6: Update existing tests that assumed Etsy is the only connector**
  - `backend/tests/test_scan.py` — replace `test_registry_filters_unconfigured_and_disabled` with:

```python
def test_registry_filters_unconfigured_and_disabled():
    configured = Settings(etsy_api_key="k", _env_file=None)
    unconfigured = Settings(etsy_api_key=None, _env_file=None)

    assert [c.name for c in build_connectors(configured, {})] == ["etsy", "google_suggest", "google_daily"]
    assert [c.name for c in build_connectors(configured, {"etsy": False})] == ["google_suggest", "google_daily"]
    assert build_connectors(configured, {}, only=["amazon"]) == []
    assert [c.name for c in build_connectors(unconfigured, {})] == ["google_suggest", "google_daily"]
    assert connector_status(unconfigured, {"etsy": False})[0] == {
        "name": "etsy", "kind": "product", "configured": False, "enabled": False
    }
```

  - `backend/tests/test_api_seeds_settings.py` `test_settings_defaults` — expected `connectors` becomes:

```python
        "connectors": [
            {"name": "etsy", "kind": "product", "configured": True, "enabled": True},
            {"name": "google_suggest", "kind": "trend", "configured": True, "enabled": True},
            {"name": "google_daily", "kind": "trend", "configured": True, "enabled": True},
        ],
```

  - `backend/tests/test_api_scans_health.py` — replace `[etsy] = client.get("/api/health/sources").json()` with `etsy = next(s for s in client.get("/api/health/sources").json() if s["name"] == "etsy")`.
  - Run the whole suite and fix any other test that hard-codes a single connector the same way (do not change production behaviour to make them pass).

- [ ] **Step 7: Run full suite** → all pass.

- [ ] **Step 8: Commit**

```bash
git add backend/app/connectors backend/tests
git commit -m "feat(connectors): add US Google Daily Trends feed and register trend sources" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Opportunity scoring (pure)

**Files:**
- Create: `backend/config/scoring.yaml`, `backend/app/analysis/scoring.py`
- Test: `backend/tests/test_scoring.py`

**Interfaces:**
- Consumes: `load_yaml` (Task 2)
- Produces:
  - Constants: `PRIMARY_METRICS = {"etsy": "views_per_day", "etsy_tags": "tag_count", "google_suggest": "suggest_score", "google_daily": "traffic"}`, `COMPETITION_KEY = ("etsy", "listing_count_tshirt")`, `ACTIVE_DAYS = 7`, `HISTORY_DAYS = 30`, `RISING_GROWTH = 0.2`, `CONVERGENCE_BONUS = 0.1`.
  - `Weights(demand=0.35, momentum=0.45, competition=0.20)` frozen dataclass; `load_weights() -> Weights` from `scoring.yaml` key `weights`.
  - `Series = list[tuple[date, float]]`; `percentile_ranks(values: dict[int, float]) -> dict[int, float]`; `series_growth(series, today) -> float | None`; `latest_recent(series, today) -> float | None`.
  - `KeywordScoreResult(keyword_id, score, demand, momentum, competition, growth, sources: tuple[str, ...], sources_rising)`.
  - `score_keywords(signals: dict[int, dict[tuple[str, str], Series]], today: date, weights: Weights = Weights()) -> list[KeywordScoreResult]` sorted by score desc then keyword_id.

Definitions (exact):
- Day offset `age = (today - d).days`. "Recent" = `0 <= age < 7`; "older" = `7 <= age < 30`.
- `latest_recent`: value at the max date among recent points, else None.
- `series_growth`: `mean(recent) / mean(older) - 1` if both non-empty and `mean(older) > 0`, else None.
- A source is active for a keyword if its primary series has a recent point. Keywords with no active source are omitted.
- `percentile_ranks`: n = len; n==1 → 1.0; else for v: `(count(x < v) + (count(x == v) - 1) / 2) / (n - 1)`.
- demand = mean over active sources of that source's percentile (computed among keywords active on that source).
- growth (reported) = mean of available source growths (sources with growth not None); momentum = `min(1, percentile(growth among keywords with growth) + 0.1 * max(0, rising - 1))` where rising = #sources with growth > 0.2; None when no growth.
- competition = min-max normalized `log1p(latest_recent(listing_count_tshirt))` among keywords that have it (all equal → 0.5); None if absent.
- score = `100 * Σ w·v / Σ w` over available components (demand, momentum, 1 − competition), rounded to 2 decimals.

- [ ] **Step 1: Create `backend/config/scoring.yaml`**

```yaml
# Trọng số điểm cơ hội (0–100). Thành phần thiếu dữ liệu bị bỏ và chia lại trọng số.
weights:
  demand: 0.35
  momentum: 0.45
  competition: 0.20
```

- [ ] **Step 2: Write the failing test `backend/tests/test_scoring.py`**

```python
from datetime import date, timedelta

import pytest

from app.analysis.scoring import (
    Weights,
    latest_recent,
    load_weights,
    percentile_ranks,
    score_keywords,
    series_growth,
)

TODAY = date(2026, 10, 5)


def days_ago(n: int) -> date:
    return TODAY - timedelta(days=n)


def test_load_weights_from_yaml():
    assert load_weights() == Weights(demand=0.35, momentum=0.45, competition=0.20)


def test_percentile_ranks():
    assert percentile_ranks({}) == {}
    assert percentile_ranks({1: 5.0}) == {1: 1.0}
    assert percentile_ranks({1: 1.0, 2: 2.0, 3: 3.0}) == {1: 0.0, 2: 0.5, 3: 1.0}
    assert percentile_ranks({1: 1.0, 2: 1.0, 3: 3.0}) == {1: 0.25, 2: 0.25, 3: 1.0}


def test_latest_recent_and_growth():
    series = [(days_ago(20), 10.0), (days_ago(10), 10.0), (days_ago(3), 12.0), (days_ago(1), 18.0)]
    assert latest_recent(series, TODAY) == 18.0
    assert series_growth(series, TODAY) == pytest.approx(0.5)  # mean(12,18)=15 vs 10
    assert latest_recent([(days_ago(8), 1.0)], TODAY) is None
    assert series_growth([(days_ago(1), 5.0)], TODAY) is None
    assert series_growth([(days_ago(1), 5.0), (days_ago(10), 0.0)], TODAY) is None


def test_score_keywords_end_to_end():
    signals = {
        # seed with rising Etsy demand and low competition
        1: {
            ("etsy", "views_per_day"): [(days_ago(14), 10.0), (days_ago(1), 20.0)],
            ("etsy", "listing_count_tshirt"): [(days_ago(1), 1000.0)],
        },
        # seed with flat demand and high competition
        2: {
            ("etsy", "views_per_day"): [(days_ago(14), 10.0), (days_ago(1), 10.0)],
            ("etsy", "listing_count_tshirt"): [(days_ago(1), 100000.0)],
        },
        # discovered suggestion: only demand, no history
        3: {("google_suggest", "suggest_score"): [(days_ago(0), 10.0)]},
        # stale keyword: no recent point → not scored
        4: {("google_daily", "traffic"): [(days_ago(9), 5000.0)]},
    }
    results = {r.keyword_id: r for r in score_keywords(signals, TODAY)}

    assert set(results) == {1, 2, 3}
    k1, k2, k3 = results[1], results[2], results[3]
    assert (k1.demand, k1.momentum, k1.competition) == (1.0, 1.0, 0.0)
    assert k1.growth == pytest.approx(1.0)
    assert (k1.sources, k1.sources_rising) == (("etsy",), 1)
    assert k1.score == 100.0
    assert (k2.demand, k2.momentum, k2.competition) == (0.0, 0.0, 1.0)
    assert k2.score == 0.0
    assert (k3.demand, k3.momentum, k3.competition, k3.growth) == (1.0, None, None, None)
    assert k3.score == 100.0  # only demand available → weight renormalized
    assert [r.keyword_id for r in score_keywords(signals, TODAY)] == [1, 3, 2]


def test_convergence_bonus_and_multi_source_demand():
    rising = [(days_ago(14), 10.0), (days_ago(1), 20.0)]
    flat = [(days_ago(14), 10.0), (days_ago(1), 10.0)]
    signals = {
        1: {("etsy", "views_per_day"): rising, ("google_suggest", "suggest_score"): rising},
        2: {("etsy", "views_per_day"): flat, ("google_suggest", "suggest_score"): rising},
        3: {("etsy", "views_per_day"): flat, ("google_suggest", "suggest_score"): flat},
    }
    results = {r.keyword_id: r for r in score_keywords(signals, TODAY, Weights(1.0, 1.0, 1.0))}
    assert results[1].sources_rising == 2
    assert results[1].momentum == 1.0  # 1.0 percentile + bonus, capped
    assert results[2].sources_rising == 1
    assert results[2].momentum == pytest.approx(0.5)
    assert results[3].momentum == 0.0
    # etsy pct 1.0 (20 vs 10,10); suggest pct 0.75 (tied 20,20 vs 10) → mean 0.875
    assert results[1].demand == pytest.approx(0.875)
```

- [ ] **Step 3: Run to verify failure** — ModuleNotFoundError.

- [ ] **Step 4: Create `backend/app/analysis/scoring.py`**

```python
"""Keyword opportunity score (spec §13). Pure functions over trend_signals series."""

import math
from bisect import bisect_left, bisect_right
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from statistics import mean

from app.config_files import load_yaml

PRIMARY_METRICS = {
    "etsy": "views_per_day",
    "etsy_tags": "tag_count",
    "google_suggest": "suggest_score",
    "google_daily": "traffic",
}
COMPETITION_KEY = ("etsy", "listing_count_tshirt")
ACTIVE_DAYS = 7
HISTORY_DAYS = 30
RISING_GROWTH = 0.2
CONVERGENCE_BONUS = 0.1

Series = list[tuple[date, float]]


@dataclass(frozen=True)
class Weights:
    demand: float = 0.35
    momentum: float = 0.45
    competition: float = 0.20


@dataclass(frozen=True)
class KeywordScoreResult:
    keyword_id: int
    score: float
    demand: float | None
    momentum: float | None
    competition: float | None
    growth: float | None
    sources: tuple[str, ...]
    sources_rising: int


def load_weights() -> Weights:
    data = load_yaml("scoring.yaml").get("weights") or {}
    defaults = Weights()
    return Weights(
        demand=float(data.get("demand", defaults.demand)),
        momentum=float(data.get("momentum", defaults.momentum)),
        competition=float(data.get("competition", defaults.competition)),
    )


def percentile_ranks(values: dict[int, float]) -> dict[int, float]:
    n = len(values)
    if n == 0:
        return {}
    if n == 1:
        return {k: 1.0 for k in values}
    ordered = sorted(values.values())
    out = {}
    for key, value in values.items():
        less = bisect_left(ordered, value)
        equal = bisect_right(ordered, value) - less
        out[key] = (less + (equal - 1) / 2) / (n - 1)
    return out


def _window(series: Series, today: date, start: int, end: int) -> list[tuple[date, float]]:
    return [(d, v) for d, v in series if start <= (today - d).days < end]


def latest_recent(series: Series, today: date) -> float | None:
    recent = _window(series, today, 0, ACTIVE_DAYS)
    return max(recent)[1] if recent else None


def series_growth(series: Series, today: date) -> float | None:
    recent = [v for _, v in _window(series, today, 0, ACTIVE_DAYS)]
    older = [v for _, v in _window(series, today, ACTIVE_DAYS, HISTORY_DAYS)]
    if not recent or not older:
        return None
    base = mean(older)
    return mean(recent) / base - 1 if base > 0 else None


def _min_max(values: dict[int, float]) -> dict[int, float]:
    if not values:
        return {}
    low, high = min(values.values()), max(values.values())
    if high == low:
        return {k: 0.5 for k in values}
    return {k: (v - low) / (high - low) for k, v in values.items()}


def score_keywords(
    signals: dict[int, dict[tuple[str, str], Series]], today: date, weights: Weights = Weights()
) -> list[KeywordScoreResult]:
    demand_raw: dict[str, dict[int, float]] = defaultdict(dict)
    growths: dict[int, dict[str, float]] = defaultdict(dict)
    competition_raw: dict[int, float] = {}
    active: dict[int, list[str]] = {}

    for keyword_id, by_metric in signals.items():
        sources = []
        for source, metric in PRIMARY_METRICS.items():
            series = by_metric.get((source, metric)) or []
            current = latest_recent(series, today)
            if current is None:
                continue
            sources.append(source)
            demand_raw[source][keyword_id] = current
            growth = series_growth(series, today)
            if growth is not None:
                growths[keyword_id][source] = growth
        if not sources:
            continue
        active[keyword_id] = sources
        listings = latest_recent(by_metric.get(COMPETITION_KEY) or [], today)
        if listings is not None:
            competition_raw[keyword_id] = math.log1p(listings)

    demand_pct = {source: percentile_ranks(values) for source, values in demand_raw.items()}
    mean_growth = {k: mean(g.values()) for k, g in growths.items() if g}
    momentum_pct = percentile_ranks(mean_growth)
    competition_norm = _min_max(competition_raw)

    results = []
    for keyword_id, sources in active.items():
        demand = mean(demand_pct[s][keyword_id] for s in sources)
        rising = sum(1 for g in growths.get(keyword_id, {}).values() if g > RISING_GROWTH)
        momentum = None
        if keyword_id in momentum_pct:
            momentum = min(1.0, momentum_pct[keyword_id] + CONVERGENCE_BONUS * max(0, rising - 1))
        competition = competition_norm.get(keyword_id)
        parts = [
            (weights.demand, demand),
            (weights.momentum, momentum),
            (weights.competition, None if competition is None else 1 - competition),
        ]
        available = [(w, v) for w, v in parts if v is not None]
        total = sum(w for w, _ in available)
        score = round(100 * sum(w * v for w, v in available) / total, 2) if total else 0.0
        results.append(
            KeywordScoreResult(
                keyword_id=keyword_id,
                score=score,
                demand=demand,
                momentum=momentum,
                competition=competition,
                growth=mean_growth.get(keyword_id),
                sources=tuple(sources),
                sources_rising=rising,
            )
        )
    return sorted(results, key=lambda r: (-r.score, r.keyword_id))
```

- [ ] **Step 5: Run tests** → all pass; full suite passes.

- [ ] **Step 6: Commit**

```bash
git add backend/config/scoring.yaml backend/app/analysis/scoring.py backend/tests/test_scoring.py
git commit -m "feat(analysis): add keyword opportunity scoring" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: Rescore pipeline (after each scan + `make rescore`)

**Files:**
- Create: `backend/app/pipeline/rescore.py`, `backend/scripts/rescore.py`
- Modify: `backend/app/pipeline/scan.py`, `Makefile`
- Test: `backend/tests/test_rescore.py`

**Interfaces:**
- Consumes: `score_keywords`, `load_weights`, `HISTORY_DAYS`, `Weights` (Task 8); `TrendSignal`, `KeywordScore`
- Produces: `rescore(session, today: date, weights: Weights | None = None) -> int` — loads signals with `today - 29 days <= date <= today`, replaces all `KeywordScore` rows for `today`, flushes (no commit), returns #rows. `run_scan` calls it once after all connectors in its own session + commit, guarded by `try/except Exception: logger.exception(...)`. `make rescore` → `cd backend && .venv/bin/python scripts/rescore.py` (rescore today UTC, print count).

- [ ] **Step 1: Write the failing test `backend/tests/test_rescore.py`**

```python
from datetime import date, timedelta

from sqlalchemy import func, select

from app.keywords import get_or_create_keyword
from app.models import KeywordScore, TrendSignal
from app.pipeline.rescore import rescore
from app.pipeline.scan import run_scan

TODAY = date(2026, 10, 5)


def add_signal(session, text, source, metric, value, d):
    kw = get_or_create_keyword(session, text)
    session.add(TrendSignal(keyword_id=kw.id, source=source, metric=metric, value=value, date=d))
    return kw


def test_rescore_writes_one_row_per_keyword_and_replaces(session):
    a = add_signal(session, "nurse", "etsy", "views_per_day", 20.0, TODAY)
    add_signal(session, "nurse", "etsy", "views_per_day", 10.0, TODAY - timedelta(days=14))
    b = add_signal(session, "dog mom", "etsy", "views_per_day", 5.0, TODAY)
    add_signal(session, "old", "etsy", "views_per_day", 5.0, TODAY - timedelta(days=40))
    session.commit()

    assert rescore(session, TODAY) == 2
    session.commit()
    assert rescore(session, TODAY) == 2  # idempotent for the same day
    session.commit()

    rows = {r.keyword_id: r for r in session.scalars(select(KeywordScore))}
    assert set(rows) == {a.id, b.id}
    assert rows[a.id].date == TODAY
    assert rows[a.id].sources == ["etsy"]
    assert rows[a.id].score > rows[b.id].score


async def test_run_scan_rescores_after_connectors(session_factory):
    with session_factory() as s:
        add_signal(s, "nurse", "etsy", "views_per_day", 20.0, TODAY)
        s.commit()

    await run_scan(session_factory, [], today=TODAY)

    with session_factory() as s:
        assert s.scalar(select(func.count()).select_from(KeywordScore)) == 1
```

- [ ] **Step 2: Run to verify failure** — ModuleNotFoundError.

- [ ] **Step 3: Create `backend/app/pipeline/rescore.py`**

```python
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.analysis.scoring import HISTORY_DAYS, Series, Weights, load_weights, score_keywords
from app.models import KeywordScore, TrendSignal


def rescore(session: Session, today: date, weights: Weights | None = None) -> int:
    """Recompute keyword_scores for `today` from the last 30 days of signals. Does not commit."""
    since = today - timedelta(days=HISTORY_DAYS - 1)
    rows = session.execute(
        select(TrendSignal.keyword_id, TrendSignal.source, TrendSignal.metric, TrendSignal.date, TrendSignal.value)
        .where(TrendSignal.date >= since, TrendSignal.date <= today)
    )
    signals: dict[int, dict[tuple[str, str], Series]] = defaultdict(lambda: defaultdict(list))
    for keyword_id, source, metric, day, value in rows:
        signals[keyword_id][(source, metric)].append((day, value))

    results = score_keywords(signals, today, weights or load_weights())
    session.execute(delete(KeywordScore).where(KeywordScore.date == today))
    session.add_all(
        KeywordScore(
            keyword_id=r.keyword_id,
            date=today,
            score=r.score,
            demand=r.demand,
            momentum=r.momentum,
            competition=r.competition,
            growth=r.growth,
            sources_rising=r.sources_rising,
            sources=list(r.sources),
        )
        for r in results
    )
    session.flush()
    return len(results)
```

- [ ] **Step 4: Edit `backend/app/pipeline/scan.py`** — import `from app.pipeline.rescore import rescore`; in `run_scan`, after `run_ids = [...]` and before the purge block, add:

```python
    try:
        with session_factory() as session:
            rescore(session, today)
            session.commit()
    except Exception:  # scoring must never break a scan
        logger.exception("Rescoring failed")
```

- [ ] **Step 5: Create `backend/scripts/rescore.py`**

```python
"""Recompute today's keyword scores from stored signals. Usage: python scripts/rescore.py"""

from datetime import datetime, timezone

from app.config import get_settings
from app.db import make_engine, make_session_factory
from app.pipeline.rescore import rescore


def main() -> None:
    today = datetime.now(timezone.utc).date()
    session_factory = make_session_factory(make_engine(get_settings().database_url))
    with session_factory() as session:
        count = rescore(session, today)
        session.commit()
    print(f"Rescored {count} keywords for {today}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Edit root `Makefile`** — add `rescore` to `.PHONY` and:

```makefile
rescore:
	cd backend && .venv/bin/python scripts/rescore.py
```

- [ ] **Step 7: Run tests** — `cd backend && .venv/bin/pytest -q` → all pass.

- [ ] **Step 8: Commit**

```bash
git add backend/app/pipeline backend/scripts/rescore.py backend/tests/test_rescore.py Makefile
git commit -m "feat(pipeline): rescore keywords after each scan and via make rescore" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 10: Trends API

**Files:**
- Create: `backend/app/api/trends.py`
- Modify: `backend/app/api/schemas.py` (append), `backend/app/main.py` (include router)
- Test: `backend/tests/test_api_trends.py`

**Interfaces:**
- Consumes: `KeywordScore`, `KeywordRelation`, `Keyword`, `Seed`, `TrendSignal`
- Produces:
  - `GET /api/trends?source=&origin=seed|discovered&pod_only=true&limit=100` → `TrendPage {date: date | null, items: [TrendOut]}` for the latest scored date, sorted by score desc then keyword_id. Filters: `pod_only` → `Keyword.is_pod_relevant`; `origin`; `source` ∈ score.sources.
  - `TrendOut`: `keyword_id, keyword, origin, is_pod_relevant, is_seed, is_new, score, demand, momentum, competition, growth, sources: list[str], sources_rising, sparkline: list[float]` (scores of the last 30 days up to the latest date, ascending by date). `is_new` = `first_seen_at.date() >= latest_date - 7 days`. `is_seed` = a Seed with that keyword text exists.
  - `GET /api/trends/{keyword_id}` → `TrendDetail {keyword_id, keyword, origin, is_pod_relevant, is_seed, trend: TrendOut | null, signals: [SignalSeries{source, metric, points: [{date, value}]}], related: [RelatedKeywordOut{keyword_id, keyword, relation: "child"|"parent", source, score: float | null, is_pod_relevant}]}`; 404 if keyword missing. Signals window: 30 days ending at the keyword's latest score date, else its latest signal date. `related` sorted by score desc (None last) then keyword text.

- [ ] **Step 1: Write the failing test `backend/tests/test_api_trends.py`**

```python
from datetime import date, datetime, timedelta

import pytest

from app.keywords import get_or_create_keyword
from app.models import KeywordRelation, KeywordScore, Seed, TrendSignal

TODAY = date(2026, 10, 5)


@pytest.fixture
def data(session):
    nurse = get_or_create_keyword(session, "nurse")
    nurse.first_seen_at = datetime(2026, 8, 1)
    gift = get_or_create_keyword(session, "nurse gift", origin="discovered", has_parent=True)
    gift.first_seen_at = datetime(2026, 10, 3)
    news = get_or_create_keyword(session, "braves dodgers game", origin="discovered")
    session.add(Seed(keyword="nurse"))
    session.add(KeywordRelation(parent_id=nurse.id, child_id=gift.id, source="etsy_tags", last_seen=TODAY))
    for kw, score, sources in ((nurse, 80.0, ["etsy"]), (gift, 60.0, ["etsy_tags"]), (news, 90.0, ["google_daily"])):
        session.add(KeywordScore(keyword_id=kw.id, date=TODAY, score=score, demand=0.5, momentum=None,
                                 competition=None, growth=None, sources_rising=0, sources=sources))
    session.add(KeywordScore(keyword_id=nurse.id, date=TODAY - timedelta(days=1), score=70.0,
                             sources_rising=0, sources=["etsy"]))
    session.add(KeywordScore(keyword_id=nurse.id, date=TODAY - timedelta(days=40), score=1.0,
                             sources_rising=0, sources=["etsy"]))
    session.add_all([
        TrendSignal(keyword_id=nurse.id, source="etsy", metric="views_per_day", value=5.0, date=TODAY - timedelta(days=1)),
        TrendSignal(keyword_id=nurse.id, source="etsy", metric="views_per_day", value=7.0, date=TODAY),
        TrendSignal(keyword_id=nurse.id, source="etsy", metric="listing_count_tshirt", value=1000.0, date=TODAY),
        TrendSignal(keyword_id=nurse.id, source="etsy", metric="views_per_day", value=1.0, date=TODAY - timedelta(days=45)),
    ])
    session.commit()
    return {"nurse": nurse.id, "gift": gift.id, "news": news.id}


def test_empty_when_no_scores(client):
    assert client.get("/api/trends").json() == {"date": None, "items": []}


def test_lists_latest_scores_pod_only_by_default(client, data):
    body = client.get("/api/trends").json()
    assert body["date"] == "2026-10-05"
    assert [i["keyword"] for i in body["items"]] == ["nurse", "nurse gift"]
    nurse, gift = body["items"]
    assert nurse["is_seed"] is True and nurse["is_new"] is False
    assert nurse["sparkline"] == [70.0, 80.0]
    assert gift["is_seed"] is False and gift["is_new"] is True and gift["origin"] == "discovered"


def test_filters(client, data):
    all_items = client.get("/api/trends?pod_only=false").json()["items"]
    assert [i["keyword"] for i in all_items] == ["braves dodgers game", "nurse", "nurse gift"]
    assert [i["keyword"] for i in client.get("/api/trends?source=etsy_tags").json()["items"]] == ["nurse gift"]
    assert [i["keyword"] for i in client.get("/api/trends?origin=seed").json()["items"]] == ["nurse"]
    assert len(client.get("/api/trends?limit=1").json()["items"]) == 1


def test_detail(client, data):
    body = client.get(f"/api/trends/{data['nurse']}").json()
    assert (body["keyword"], body["is_seed"], body["trend"]["score"]) == ("nurse", True, 80.0)
    series = {(s["source"], s["metric"]): s["points"] for s in body["signals"]}
    assert [p["value"] for p in series[("etsy", "views_per_day")]] == [5.0, 7.0]  # 45-day-old point excluded
    assert ("etsy", "listing_count_tshirt") in series
    assert body["related"] == [{
        "keyword_id": data["gift"], "keyword": "nurse gift", "relation": "child",
        "source": "etsy_tags", "score": 60.0, "is_pod_relevant": True,
    }]
    child = client.get(f"/api/trends/{data['gift']}").json()
    assert child["related"][0]["relation"] == "parent"
    assert child["related"][0]["keyword"] == "nurse"


def test_detail_404(client):
    assert client.get("/api/trends/999").status_code == 404
```

- [ ] **Step 2: Run to verify failure** — 404s.

- [ ] **Step 3: Append to `backend/app/api/schemas.py`** (add `from datetime import date` next to the datetime import and `Literal` from typing):

```python
class TrendOut(BaseModel):
    keyword_id: int
    keyword: str
    origin: str
    is_pod_relevant: bool
    is_seed: bool
    is_new: bool
    score: float
    demand: float | None
    momentum: float | None
    competition: float | None
    growth: float | None
    sources: list[str]
    sources_rising: int
    sparkline: list[float]


class TrendPage(BaseModel):
    date: date | None
    items: list[TrendOut]


class SignalPoint(BaseModel):
    date: date
    value: float


class SignalSeries(BaseModel):
    source: str
    metric: str
    points: list[SignalPoint]


class RelatedKeywordOut(BaseModel):
    keyword_id: int
    keyword: str
    relation: Literal["child", "parent"]
    source: str
    score: float | None
    is_pod_relevant: bool


class TrendDetail(BaseModel):
    keyword_id: int
    keyword: str
    origin: str
    is_pod_relevant: bool
    is_seed: bool
    trend: TrendOut | None
    signals: list[SignalSeries]
    related: list[RelatedKeywordOut]
```

Note: a field named `date` with annotation `date` inside a pydantic model shadows the type for later annotations in the same class body — in `TrendPage` and `SignalPoint` the `date` field is declared with the type before it is shadowed, which works; if pydantic raises a type-resolution error, import `datetime` module as `import datetime as dt` and annotate `dt.date`.

- [ ] **Step 4: Create `backend/app/api/trends.py`**

```python
from collections import defaultdict
from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analysis.scoring import HISTORY_DAYS
from app.api.deps import get_session
from app.api.schemas import (
    RelatedKeywordOut,
    SignalPoint,
    SignalSeries,
    TrendDetail,
    TrendOut,
    TrendPage,
)
from app.models import Keyword, KeywordRelation, KeywordScore, Seed, TrendSignal

router = APIRouter(prefix="/api")
NEW_DAYS = 7


def _seed_texts(session: Session) -> set[str]:
    return set(session.scalars(select(Seed.keyword)))


def _sparklines(session: Session, keyword_ids: list[int], latest: date) -> dict[int, list[float]]:
    if not keyword_ids:
        return {}
    since = latest - timedelta(days=HISTORY_DAYS - 1)
    rows = session.execute(
        select(KeywordScore.keyword_id, KeywordScore.score)
        .where(KeywordScore.keyword_id.in_(keyword_ids), KeywordScore.date >= since, KeywordScore.date <= latest)
        .order_by(KeywordScore.date)
    )
    out: dict[int, list[float]] = defaultdict(list)
    for keyword_id, score in rows:
        out[keyword_id].append(score)
    return out


def _trend_out(
    score: KeywordScore, keyword: Keyword, seeds: set[str], sparkline: list[float]
) -> TrendOut:
    return TrendOut(
        keyword_id=keyword.id,
        keyword=keyword.text,
        origin=keyword.origin,
        is_pod_relevant=keyword.is_pod_relevant,
        is_seed=keyword.text in seeds,
        is_new=keyword.first_seen_at.date() >= score.date - timedelta(days=NEW_DAYS),
        score=score.score,
        demand=score.demand,
        momentum=score.momentum,
        competition=score.competition,
        growth=score.growth,
        sources=list(score.sources or []),
        sources_rising=score.sources_rising,
        sparkline=sparkline,
    )


@router.get("/trends", response_model=TrendPage)
def list_trends(
    source: str | None = None,
    origin: Literal["seed", "discovered"] | None = None,
    pod_only: bool = True,
    limit: int = Query(100, ge=1, le=500),
    session: Session = Depends(get_session),
) -> TrendPage:
    latest = session.scalar(select(func.max(KeywordScore.date)))
    if latest is None:
        return TrendPage(date=None, items=[])
    rows = session.execute(
        select(KeywordScore, Keyword)
        .join(Keyword, Keyword.id == KeywordScore.keyword_id)
        .where(KeywordScore.date == latest)
    ).all()
    selected = [
        (score, keyword)
        for score, keyword in rows
        if (not pod_only or keyword.is_pod_relevant)
        and (origin is None or keyword.origin == origin)
        and (source is None or source in (score.sources or []))
    ]
    selected.sort(key=lambda row: (-row[0].score, row[1].id))
    selected = selected[:limit]
    seeds = _seed_texts(session)
    history = _sparklines(session, [k.id for _, k in selected], latest)
    return TrendPage(
        date=latest,
        items=[_trend_out(s, k, seeds, history.get(k.id, [])) for s, k in selected],
    )


@router.get("/trends/{keyword_id}", response_model=TrendDetail)
def trend_detail(keyword_id: int, session: Session = Depends(get_session)) -> TrendDetail:
    keyword = session.get(Keyword, keyword_id)
    if keyword is None:
        raise HTTPException(status_code=404, detail="Keyword not found")
    seeds = _seed_texts(session)
    latest_score = session.scalar(
        select(KeywordScore).where(KeywordScore.keyword_id == keyword_id).order_by(KeywordScore.date.desc()).limit(1)
    )
    trend = None
    if latest_score is not None:
        sparkline = _sparklines(session, [keyword_id], latest_score.date).get(keyword_id, [])
        trend = _trend_out(latest_score, keyword, seeds, sparkline)

    anchor = latest_score.date if latest_score else session.scalar(
        select(func.max(TrendSignal.date)).where(TrendSignal.keyword_id == keyword_id)
    )
    signals: list[SignalSeries] = []
    if anchor is not None:
        since = anchor - timedelta(days=HISTORY_DAYS - 1)
        grouped: dict[tuple[str, str], list[SignalPoint]] = defaultdict(list)
        for source, metric, day, value in session.execute(
            select(TrendSignal.source, TrendSignal.metric, TrendSignal.date, TrendSignal.value)
            .where(TrendSignal.keyword_id == keyword_id, TrendSignal.date >= since, TrendSignal.date <= anchor)
            .order_by(TrendSignal.source, TrendSignal.metric, TrendSignal.date)
        ):
            grouped[(source, metric)].append(SignalPoint(date=day, value=value))
        signals = [SignalSeries(source=s, metric=m, points=p) for (s, m), p in grouped.items()]

    return TrendDetail(
        keyword_id=keyword.id,
        keyword=keyword.text,
        origin=keyword.origin,
        is_pod_relevant=keyword.is_pod_relevant,
        is_seed=keyword.text in seeds,
        trend=trend,
        signals=signals,
        related=_related(session, keyword_id),
    )


def _related(session: Session, keyword_id: int) -> list[RelatedKeywordOut]:
    pairs = [
        (rel.child_id, "child", rel.source)
        for rel in session.scalars(select(KeywordRelation).where(KeywordRelation.parent_id == keyword_id))
    ] + [
        (rel.parent_id, "parent", rel.source)
        for rel in session.scalars(select(KeywordRelation).where(KeywordRelation.child_id == keyword_id))
    ]
    out = []
    for other_id, relation, source in pairs:
        other = session.get(Keyword, other_id)
        score = session.scalar(
            select(KeywordScore.score).where(KeywordScore.keyword_id == other_id).order_by(KeywordScore.date.desc()).limit(1)
        )
        out.append(
            RelatedKeywordOut(
                keyword_id=other.id, keyword=other.text, relation=relation, source=source,
                score=score, is_pod_relevant=other.is_pod_relevant,
            )
        )
    out.sort(key=lambda r: (r.score is None, -(r.score or 0), r.keyword))
    return out
```

Wrap any line over 100 characters when writing the file.

- [ ] **Step 5: Edit `backend/app/main.py`** — import `trends` alongside the other api modules and add it to the router loop: `for module in (products, seeds, settings_api, scans, health, trends):`.

- [ ] **Step 6: Run tests** → all pass.

- [ ] **Step 7: Commit**

```bash
git add backend/app/api backend/app/main.py backend/tests/test_api_trends.py
git commit -m "feat(api): add trend radar list and keyword detail endpoints" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 11: Frontend data layer, nav, product card

**Files:**
- Modify: `frontend/lib/api.ts`, `frontend/lib/format.ts`, `frontend/app/layout.tsx`, `frontend/app/products/page.tsx`
- Rewrite: `frontend/components/ProductCard.tsx`
- Create: `frontend/components/Sparkline.tsx`
- Install: `recharts`

**Interfaces:**
- Produces (lib/api.ts): `Product` gains `views: number | null; shop_sold_count: number | null; velocity_metric: "reviews" | "views" | "favorites" | null`. Types `TrendItem, TrendPage, TrendQuery, SignalSeries, RelatedKeyword, TrendDetail` mirroring backend schemas. `api.listTrends(q?: TrendQuery)`, `api.getTrend(id: number)`.
- Produces (lib/format.ts): `SOURCE_LABEL: Record<string, string>`, `METRIC_LABEL: Record<string, string>`, `formatGrowth(g: number | null): string`, `formatNumber(n: number | null): string`.
- Produces: `<Sparkline values={number[]} />`.

- [ ] **Step 1: Install Recharts** — `cd frontend && npm install recharts`

- [ ] **Step 2: Edit `frontend/lib/api.ts`**
  - In `Product`, after `rating: number | null;` add:

```ts
  views: number | null;
  shop_sold_count: number | null;
  velocity_metric: "reviews" | "views" | "favorites" | null;
```

  - Before `async function request` add:

```ts
export type TrendItem = {
  keyword_id: number;
  keyword: string;
  origin: "seed" | "discovered";
  is_pod_relevant: boolean;
  is_seed: boolean;
  is_new: boolean;
  score: number;
  demand: number | null;
  momentum: number | null;
  competition: number | null;
  growth: number | null;
  sources: string[];
  sources_rising: number;
  sparkline: number[];
};

export type TrendPage = { date: string | null; items: TrendItem[] };

export type TrendQuery = {
  source?: string;
  origin?: "seed" | "discovered";
  pod_only?: boolean;
  limit?: number;
};

export type SignalSeries = { source: string; metric: string; points: { date: string; value: number }[] };

export type RelatedKeyword = {
  keyword_id: number;
  keyword: string;
  relation: "child" | "parent";
  source: string;
  score: number | null;
  is_pod_relevant: boolean;
};

export type TrendDetail = {
  keyword_id: number;
  keyword: string;
  origin: "seed" | "discovered";
  is_pod_relevant: boolean;
  is_seed: boolean;
  trend: TrendItem | null;
  signals: SignalSeries[];
  related: RelatedKeyword[];
};
```

  - Add to the `api` object:

```ts
  listTrends: (q: TrendQuery = {}) =>
    request<TrendPage>(
      `/api/trends${toQuery({ ...q, pod_only: q.pod_only === undefined ? undefined : String(q.pod_only) })}`,
    ),
  getTrend: (id: number) => request<TrendDetail>(`/api/trends/${id}`),
```

- [ ] **Step 3: Append to `frontend/lib/format.ts`**

```ts
export const SOURCE_LABEL: Record<string, string> = {
  etsy: "Etsy",
  etsy_tags: "Etsy tag",
  google_suggest: "Google gợi ý",
  google_daily: "Google xu hướng ngày",
};

export const METRIC_LABEL: Record<string, string> = {
  views_per_day: "Lượt xem TB/ngày (shop US)",
  us_listing_count: "Số listing áo shop US (top 100 × 3)",
  new_listings_30d: "Listing mới ≤ 30 ngày (shop US)",
  listing_count_tshirt: "Tổng listing Etsy (shirt)",
  listing_count_sweatshirt: "Tổng listing Etsy (sweatshirt)",
  listing_count_hoodie: "Tổng listing Etsy (hoodie)",
  tag_count: "Số listing shop US dùng tag",
  suggest_score: "Thứ hạng gợi ý Google (10 = đầu tiên)",
  traffic: "Lượt tìm kiếm ước tính (US)",
};

export function formatGrowth(growth: number | null): string {
  if (growth === null) return "—";
  const pct = Math.round(growth * 100);
  return `${pct > 0 ? "+" : ""}${pct}%`;
}

export function formatNumber(n: number | null): string {
  if (n === null) return "—";
  return new Intl.NumberFormat("en-US", { notation: n >= 10000 ? "compact" : "standard", maximumFractionDigits: 1 }).format(n);
}
```

- [ ] **Step 4: Create `frontend/components/Sparkline.tsx`**

```tsx
export default function Sparkline({ values, width = 96, height = 24 }: { values: number[]; width?: number; height?: number }) {
  if (values.length < 2) return <span className="text-xs text-zinc-400">—</span>;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const step = width / (values.length - 1);
  const points = values
    .map((v, i) => `${(i * step).toFixed(1)},${(height - 1 - ((v - min) / span) * (height - 2)).toFixed(1)}`)
    .join(" ");
  const rising = values[values.length - 1] >= values[0];
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} aria-hidden="true">
      <polyline points={points} fill="none" strokeWidth={1.5} className={rising ? "stroke-green-600" : "stroke-red-500"} />
    </svg>
  );
}
```

- [ ] **Step 5: Rewrite `frontend/components/ProductCard.tsx`**

```tsx
import type { Product } from "@/lib/api";
import { PRODUCT_TYPE_LABEL, formatNumber, formatPrice, timeAgo } from "@/lib/format";

const METRIC_UNIT = { reviews: "reviews", views: "lượt xem", favorites: "favorites" } as const;

export default function ProductCard({ product }: { product: Product }) {
  const metric =
    product.velocity_metric ?? (product.reviews !== null ? "reviews" : product.views !== null ? "views" : "favorites");
  const count = product[metric];
  const delta = product.delta_7d;

  return (
    <a
      href={product.url}
      target="_blank"
      rel="noopener noreferrer"
      className="group flex flex-col overflow-hidden rounded-lg border border-zinc-200 bg-white hover:shadow-md"
    >
      <div className="relative aspect-square bg-zinc-100">
        {product.image_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={product.image_url} alt={product.title} className="h-full w-full object-cover" loading="lazy" />
        ) : (
          <div className="flex h-full items-center justify-center text-xs text-zinc-400">Không có ảnh</div>
        )}
        {product.hot && (
          <span className="absolute left-2 top-2 rounded bg-orange-500 px-1.5 py-0.5 text-xs font-semibold text-white">
            🔥 Hot
          </span>
        )}
        <span className="absolute right-2 top-2 rounded bg-white/90 px-1.5 py-0.5 text-xs uppercase text-zinc-600">
          {product.source}
        </span>
      </div>
      <div className="flex flex-1 flex-col gap-1 p-3 text-sm">
        <p className="line-clamp-2 font-medium group-hover:underline">{product.title}</p>
        <div className="flex items-center justify-between">
          <span className="font-semibold">{formatPrice(product.price, product.currency)}</span>
          <span className="text-xs text-zinc-500">{PRODUCT_TYPE_LABEL[product.product_type]}</span>
        </div>
        <p className="text-xs text-zinc-600">
          {formatNumber(count)} {METRIC_UNIT[metric]}
          {delta !== null && (
            <span className={delta > 0 ? "ml-1 text-green-600" : "ml-1 text-zinc-400"}>
              ({delta > 0 ? "+" : ""}
              {Math.round(delta)} / 7 ngày)
            </span>
          )}
          {metric !== "favorites" && product.favorites !== null && (
            <span className="ml-1 text-zinc-400">· {formatNumber(product.favorites)} favorites</span>
          )}
        </p>
        <p className="text-xs text-zinc-500">
          {product.shop_name ?? "—"}
          {product.shop_sold_count !== null && <> · shop đã bán {formatNumber(product.shop_sold_count)}</>} · đăng{" "}
          {timeAgo(product.listed_at)}
        </p>
        {product.keywords.length > 0 && (
          <div className="mt-auto flex flex-wrap gap-1 pt-1">
            {product.keywords.map((k) => (
              <span key={k} className="rounded bg-zinc-100 px-1.5 py-0.5 text-xs text-zinc-600">
                {k}
              </span>
            ))}
          </div>
        )}
      </div>
    </a>
  );
}
```

- [ ] **Step 6: Edit `frontend/app/layout.tsx`** — in the `<nav>`, after the "POD Trend Radar" span, insert a first link:

```tsx
            <Link href="/" className="text-zinc-600 hover:text-zinc-900">
              Trend Radar
            </Link>
```

- [ ] **Step 7: Edit `frontend/app/products/page.tsx`** — change the `reviews` sort label to `"Phổ biến (reviews/lượt xem)"`, and the proxy note to: `Lượt xem / favorites / reviews và mức tăng 7 ngày là chỉ số ước tính (proxy), không phải doanh số thật. Chỉ hiển thị shop ở Mỹ. 🔥 = top 10% tăng trưởng trong cùng nguồn và loại áo.`

- [ ] **Step 8: Verify** — `cd frontend && npm run lint && npm run build` → no errors.

- [ ] **Step 9: Commit**

```bash
git add frontend
git commit -m "feat(frontend): add trend API client, sparkline and richer product cards" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 12: Trend Radar page

**Files:**
- Rewrite: `frontend/app/page.tsx`

**Interfaces:**
- Consumes: `api.listTrends`, `api.addSeed`, `ApiError`, `TrendPage`, `TrendQuery`, `Sparkline`, `SourceHealthBanner`, `SOURCE_LABEL`, `formatGrowth`
- Produces: route `/` = Trend Radar table.

Lint note: set state only in promise callbacks (keyed-result pattern), as in `/products`.

- [ ] **Step 1: Rewrite `frontend/app/page.tsx`**

```tsx
"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import Sparkline from "@/components/Sparkline";
import SourceHealthBanner from "@/components/SourceHealthBanner";
import { ApiError, api, type TrendPage, type TrendQuery } from "@/lib/api";
import { SOURCE_LABEL, formatGrowth } from "@/lib/format";

type Result = { key: string; data?: TrendPage; error?: string };

const selectClass = "rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-sm";

export default function TrendRadarPage() {
  const [query, setQuery] = useState<TrendQuery>({ pod_only: true, limit: 100 });
  const [tick, setTick] = useState(0);
  const [result, setResult] = useState<Result | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const key = `${JSON.stringify(query)}#${tick}`;
  const loading = result?.key !== key;

  useEffect(() => {
    let cancelled = false;
    api
      .listTrends(query)
      .then((data) => !cancelled && setResult({ key, data }))
      .catch((err) => !cancelled && setResult({ key, error: String(err) }));
    return () => {
      cancelled = true;
    };
  }, [key, query]);

  async function follow(keyword: string) {
    try {
      await api.addSeed(keyword);
      setMessage(`Đã thêm “${keyword}” vào watchlist — lần quét tới sẽ lấy sản phẩm Etsy (shop US) cho keyword này.`);
      setTick((t) => t + 1);
    } catch (err) {
      setMessage(err instanceof ApiError && err.status === 409 ? `“${keyword}” đã có trong watchlist.` : String(err));
    }
  }

  const items = result?.data?.items ?? [];

  return (
    <div>
      <SourceHealthBanner />
      <div className="mb-2 flex flex-wrap items-center gap-3">
        <h1 className="mr-auto text-xl font-semibold">Trend Radar</h1>
        <select
          className={selectClass}
          value={query.source ?? ""}
          onChange={(e) => setQuery((q) => ({ ...q, source: e.target.value || undefined }))}
        >
          <option value="">Tất cả nguồn</option>
          {Object.entries(SOURCE_LABEL).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
        <select
          className={selectClass}
          value={query.origin ?? ""}
          onChange={(e) =>
            setQuery((q) => ({ ...q, origin: (e.target.value || undefined) as TrendQuery["origin"] }))
          }
        >
          <option value="">Seed + khám phá</option>
          <option value="seed">Chỉ seed</option>
          <option value="discovered">Chỉ ngách khám phá</option>
        </select>
        <label className="flex items-center gap-1 text-sm">
          <input
            type="checkbox"
            checked={query.pod_only ?? true}
            onChange={(e) => setQuery((q) => ({ ...q, pod_only: e.target.checked }))}
          />
          Chỉ POD
        </label>
      </div>
      <p className="mb-4 text-xs text-zinc-500">
        Điểm 0–100 = nhu cầu (35%) + đà tăng (45%) + ít cạnh tranh (20%), tính trên dữ liệu thị trường Mỹ: Etsy (chỉ shop
        US), Google gợi ý (US), Google xu hướng ngày (US). Đà tăng cần ≥ 8 ngày dữ liệu.
        {result?.data?.date && <> Cập nhật: {result.data.date}.</>}
      </p>
      {message && <p className="mb-3 rounded-md bg-zinc-100 p-3 text-sm">{message}</p>}
      {result?.error && !loading && <p className="text-sm text-red-600">Không tải được dữ liệu: {result.error}</p>}
      {loading && <p className="text-sm text-zinc-500">Đang tải…</p>}
      {!loading && result?.data && items.length === 0 && (
        <p className="text-sm text-zinc-500">
          Chưa có điểm. Thêm keyword trong <Link href="/settings" className="underline">Cài đặt</Link> rồi bấm “Quét ngay”.
        </p>
      )}

      {items.length > 0 && (
        <table className="w-full rounded-md border border-zinc-200 bg-white text-left text-sm">
          <thead className="bg-zinc-50 text-xs uppercase text-zinc-500">
            <tr>
              <th className="px-3 py-2">#</th>
              <th className="px-3 py-2">Keyword</th>
              <th className="px-3 py-2">Điểm</th>
              <th className="px-3 py-2">Tăng trưởng</th>
              <th className="px-3 py-2">Nguồn</th>
              <th className="px-3 py-2">30 ngày</th>
              <th className="px-3 py-2"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-200">
            {items.map((item, index) => (
              <tr key={item.keyword_id}>
                <td className="px-3 py-2 text-zinc-400">{index + 1}</td>
                <td className="px-3 py-2">
                  <Link href={`/trends/${item.keyword_id}`} className="font-medium hover:underline">
                    {item.keyword}
                  </Link>
                  {item.is_new && <span className="ml-2 rounded bg-blue-100 px-1.5 py-0.5 text-xs text-blue-800">Mới</span>}
                  <span className="ml-2 text-xs text-zinc-400">{item.is_seed ? "seed" : "khám phá"}</span>
                </td>
                <td className="px-3 py-2 font-semibold">{Math.round(item.score)}</td>
                <td className={`px-3 py-2 ${item.growth !== null && item.growth > 0 ? "text-green-700" : "text-zinc-500"}`}>
                  {formatGrowth(item.growth)}
                </td>
                <td className="px-3 py-2">
                  <div className="flex flex-wrap gap-1">
                    {item.sources.map((s) => (
                      <span key={s} className="rounded bg-zinc-100 px-1.5 py-0.5 text-xs text-zinc-600">
                        {SOURCE_LABEL[s] ?? s}
                      </span>
                    ))}
                    {item.sources_rising > 0 && <span className="text-xs text-green-700">↑{item.sources_rising}</span>}
                  </div>
                </td>
                <td className="px-3 py-2">
                  <Sparkline values={item.sparkline} />
                </td>
                <td className="px-3 py-2 text-right">
                  {!item.is_seed && (
                    <button
                      onClick={() => follow(item.keyword)}
                      className="rounded border border-zinc-300 px-2 py-1 text-xs hover:bg-zinc-50"
                    >
                      + Theo dõi
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Verify** — `cd frontend && npm run lint && npm run build` → no errors (fix minimal lint issues such as unescaped quotes if reported, and record them).

- [ ] **Step 3: Commit**

```bash
git add frontend/app/page.tsx
git commit -m "feat(frontend): add Trend Radar page" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 13: Keyword detail page

**Files:**
- Create: `frontend/app/trends/[id]/page.tsx`

**Interfaces:**
- Consumes: `api.getTrend`, `api.listProducts`, `api.addSeed`, `ApiError`, `TrendDetail`, `ProductPage`, `ProductCard`, `SOURCE_LABEL`, `METRIC_LABEL`, `formatGrowth`, `formatNumber`; Recharts `LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid, ResponsiveContainer`
- Produces: route `/trends/[id]`.

- [ ] **Step 1: Create `frontend/app/trends/[id]/page.tsx`**

```tsx
"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import ProductCard from "@/components/ProductCard";
import { ApiError, api, type ProductPage, type TrendDetail } from "@/lib/api";
import { METRIC_LABEL, SOURCE_LABEL, formatGrowth, formatNumber } from "@/lib/format";

type Loaded = { key: string; detail?: TrendDetail; products?: ProductPage; error?: string };

function pct(value: number | null): string {
  return value === null ? "—" : `${Math.round(value * 100)}%`;
}

export default function TrendDetailPage() {
  const params = useParams<{ id: string }>();
  const id = Number(params.id);
  const [tick, setTick] = useState(0);
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const key = `${id}#${tick}`;
  const loading = loaded?.key !== key;

  useEffect(() => {
    let cancelled = false;
    Promise.all([api.getTrend(id), api.listProducts({ keyword_id: id, sort: "velocity", limit: 20 })])
      .then(([detail, products]) => !cancelled && setLoaded({ key, detail, products }))
      .catch((err) =>
        !cancelled &&
        setLoaded({ key, error: err instanceof ApiError && err.status === 404 ? "Không tìm thấy keyword." : String(err) }),
      );
    return () => {
      cancelled = true;
    };
  }, [id, key]);

  async function follow(keyword: string) {
    try {
      await api.addSeed(keyword);
      setMessage("Đã thêm vào watchlist — lần quét tới sẽ lấy sản phẩm Etsy (shop US).");
      setTick((t) => t + 1);
    } catch (err) {
      setMessage(err instanceof ApiError && err.status === 409 ? "Keyword đã có trong watchlist." : String(err));
    }
  }

  if (loading) return <p className="text-sm text-zinc-500">Đang tải…</p>;
  if (loaded?.error || !loaded?.detail) return <p className="text-sm text-red-600">{loaded?.error}</p>;
  const { detail, products } = loaded;
  const trend = detail.trend;

  return (
    <div className="space-y-8">
      <div>
        <Link href="/" className="text-sm text-zinc-500 hover:underline">
          ← Trend Radar
        </Link>
        <div className="mt-2 flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-semibold">{detail.keyword}</h1>
          <span className="rounded bg-zinc-100 px-2 py-0.5 text-xs text-zinc-600">
            {detail.is_seed ? "seed" : "ngách khám phá"}
          </span>
          {!detail.is_pod_relevant && (
            <span className="rounded bg-amber-100 px-2 py-0.5 text-xs text-amber-800">có thể không phải POD</span>
          )}
          {!detail.is_seed && (
            <button
              onClick={() => follow(detail.keyword)}
              className="rounded border border-zinc-300 px-2 py-1 text-xs hover:bg-zinc-50"
            >
              + Theo dõi
            </button>
          )}
        </div>
        {message && <p className="mt-3 rounded-md bg-zinc-100 p-3 text-sm">{message}</p>}
      </div>

      <section className="grid grid-cols-2 gap-3 sm:grid-cols-5">
        {[
          ["Điểm", trend ? String(Math.round(trend.score)) : "—"],
          ["Nhu cầu", pct(trend?.demand ?? null)],
          ["Đà tăng", pct(trend?.momentum ?? null)],
          ["Cạnh tranh", pct(trend?.competition ?? null)],
          ["Tăng trưởng", formatGrowth(trend?.growth ?? null)],
        ].map(([label, value]) => (
          <div key={label} className="rounded-md border border-zinc-200 bg-white p-3">
            <p className="text-xs text-zinc-500">{label}</p>
            <p className="text-lg font-semibold">{value}</p>
          </div>
        ))}
      </section>

      <section className="space-y-3">
        <h2 className="font-semibold">Tín hiệu 30 ngày (thị trường Mỹ)</h2>
        {detail.signals.length === 0 && <p className="text-sm text-zinc-500">Chưa có tín hiệu.</p>}
        <div className="grid gap-4 md:grid-cols-2">
          {detail.signals.map((series) => (
            <div key={`${series.source}/${series.metric}`} className="rounded-md border border-zinc-200 bg-white p-3">
              <p className="mb-2 text-sm font-medium">
                {SOURCE_LABEL[series.source] ?? series.source} · {METRIC_LABEL[series.metric] ?? series.metric}
              </p>
              {series.points.length < 2 ? (
                <p className="text-sm text-zinc-600">
                  {formatNumber(series.points[0]?.value ?? null)}{" "}
                  <span className="text-xs text-zinc-400">(cần ≥ 2 ngày để vẽ biểu đồ)</span>
                </p>
              ) : (
                <div className="h-40">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={series.points}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#e4e4e7" />
                      <XAxis dataKey="date" tick={{ fontSize: 10 }} />
                      <YAxis tick={{ fontSize: 10 }} width={48} />
                      <Tooltip />
                      <Line type="monotone" dataKey="value" stroke="#ea580c" dot={false} strokeWidth={2} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              )}
            </div>
          ))}
        </div>
      </section>

      <section className="space-y-3">
        <h2 className="font-semibold">Keyword liên quan</h2>
        {detail.related.length === 0 && <p className="text-sm text-zinc-500">Chưa có.</p>}
        <div className="flex flex-wrap gap-2">
          {detail.related.map((r) => (
            <Link
              key={`${r.relation}-${r.keyword_id}-${r.source}`}
              href={`/trends/${r.keyword_id}`}
              className="rounded-full border border-zinc-300 bg-white px-3 py-1 text-sm hover:bg-zinc-50"
            >
              {r.relation === "parent" ? "↑ " : ""}
              {r.keyword}
              <span className="ml-1 text-xs text-zinc-400">
                {r.score !== null ? Math.round(r.score) : "—"} · {SOURCE_LABEL[r.source] ?? r.source}
              </span>
            </Link>
          ))}
        </div>
      </section>

      <section className="space-y-3">
        <h2 className="font-semibold">Sản phẩm Etsy (shop US)</h2>
        {!detail.is_seed && (products?.items.length ?? 0) === 0 && (
          <p className="text-sm text-zinc-500">Theo dõi keyword này để lấy sản phẩm Etsy từ lần quét tới.</p>
        )}
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
          {products?.items.map((p) => <ProductCard key={p.id} product={p} />)}
        </div>
      </section>
    </div>
  );
}
```

- [ ] **Step 2: Verify** — `cd frontend && npm run lint && npm run build` → no errors; build lists `/trends/[id]`.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/trends
git commit -m "feat(frontend): add keyword detail page with signal charts" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 14: README + live end-to-end check

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update `README.md`** — change the intro line to describe Phase 1 + 2, and add a section after "Chạy":

```markdown
## Trend Radar (Phase 2)

Nguồn dữ liệu (chỉ thị trường Mỹ):
- **Etsy** — chỉ shop ở Mỹ, giá USD: lượt xem TB/ngày, số listing mới ≤ 30 ngày, tổng listing (cạnh tranh), tag phổ biến → ngách con.
- **Google gợi ý (US)** — cụm từ người Mỹ gõ sau "<keyword> shirt/hoodie/sweatshirt" → ngách con.
- **Google xu hướng ngày (US)** — sự kiện/tìm kiếm nóng trong ngày (đã lọc theo POD).

Điểm 0–100 = nhu cầu 35% + đà tăng 45% + ít cạnh tranh 20% (chỉnh trong `backend/config/scoring.yaml`).
Bộ lọc POD chỉnh trong `backend/config/pod_filter.yaml`. Đà tăng cần ≥ 8 ngày dữ liệu (quét hằng ngày).
Sau khi đổi cấu hình: `make rescore`.

Bấm **+ Theo dõi** ở một ngách khám phá để Etsy quét sản phẩm cho ngách đó từ lần sau.
TikTok Creative Center và Google Trends (biểu đồ quan tâm) chưa hỗ trợ: cả hai chặn truy cập tự động.
```

- [ ] **Step 2: Run backend tests and frontend checks** — `make test` and `cd frontend && npm run lint && npm run build` → all pass.

- [ ] **Step 3: Live end-to-end (real network; `backend/.env` has a real ETSY_API_KEY)**

```bash
make migrate
make smoke        # expect [ok] for etsy, google_suggest, google_daily
cd backend && .venv/bin/uvicorn --factory app.main:create_app --port 8000 &   # note PID
curl -s -X POST localhost:8000/api/seeds -H 'Content-Type: application/json' -d '{"keyword":"nurse"}'
curl -s -X POST localhost:8000/api/seeds -H 'Content-Type: application/json' -d '{"keyword":"dog mom"}'
curl -s -X POST localhost:8000/api/scans -H 'Content-Type: application/json' -d '{}'
# poll until no run is "running" (Etsy ~2 seeds × 6 calls; suggest 6 calls at 1/s)
curl -s localhost:8000/api/scans | head -c 600
curl -s 'localhost:8000/api/trends?limit=10' | head -c 1500
curl -s 'localhost:8000/api/products?limit=3' | head -c 800     # shop_sold_count/views present, all USD
```

Expected: three scan runs `ok` (or `partial` with explained errors); `/api/trends` has items including seeds and discovered niches (e.g. tags like "nurse gift", suggestions like "funny nurse shirts"); products all `currency: "USD"`. Then `cd frontend && npm run build && npx next start -p 3000 &` and check `/`, `/trends/<id of nurse>`, `/products` return 200. Stop both servers. Record outputs in the report. If the live run reveals a bug, report it (do not silently patch unrelated code).

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: document Trend Radar sources, scoring and configuration" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
