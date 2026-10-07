# Watchlist page + Alerts (Telegram & "Tin mới") Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Per-keyword Watchlist page, keyword filter on Etsy Listing Signals, and alerts (stored for an in-app "Tin mới" page and pushed to Telegram) after every scan.

**Architecture:** Pure alert rules in `app/analysis/alerts.py` (plain dataclasses in/out); `app/services/alerts.py` loads DB data, applies rules + dedupe, inserts `alerts` rows; `app/notify/telegram.py` sends unsent alerts. Both run at the end of `run_scan` inside try/except so they never fail a scan. New FastAPI routers `alerts` and `watchlist`; Next.js pages `/watchlist` and `/alerts` in the existing "Press Room" UI system.

**Tech Stack:** FastAPI, SQLAlchemy 2, Alembic, SQLite, httpx, respx, pytest-asyncio; Next.js 16 App Router, React 19, Tailwind v4.

Spec: `docs/superpowers/specs/2026-10-07-watchlist-alerts-design.md`.

## Global Constraints

- Backend commands run in `backend/` with `.venv/bin/...` (e.g. `.venv/bin/pytest -q`). Frontend in `frontend/`: `npm run lint`, `npx tsc --noEmit`, `npm run build`.
- UI copy is Vietnamese; follow the Press Room components in `frontend/components/ui/` (Card, Section, PageHeader, StatusBadge, HalftoneMeter, Delta, Button/ButtonLink, Select, EmptyState, Notice, ImageZoom). Tokens: paper/sheet/ink/ink-2/rule/cyan/magenta/yellow/go/stop. Mono numbers (`font-mono`).
- Secrets: `TELEGRAM_BOT_TOKEN` lives only in `backend/.env`; never logged, never returned by any API, never printed.
- Alerts/Telegram failures must never change a scan's status.
- Thresholds (from `backend/config/alerts.yaml`): `niche_min_score: 60`, `niche_min_growth: 0.20`, `amazon_top_n: 20`, `cooldown_days: 7`, `telegram_max_items: 5`.
- `KeywordScore.growth` is a fraction (0.35 = +35%) and may be None.
- Every commit message ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Never commit `.superpowers/`, `backend/.env`, `backend/data/`, `frontend/.env.local`.

---

### Task 1: Alert model, migration, config and settings

**Files:**
- Modify: `backend/app/models.py` (add `Alert`; add `Index` to the sqlalchemy import)
- Create: `backend/alembic/versions/<rev>_alerts.py` (autogenerate)
- Create: `backend/config/alerts.yaml`
- Create: `backend/app/analysis/alerts.py` (config part only in this task)
- Modify: `backend/app/config.py` (Telegram + APP_URL settings)
- Modify: `backend/.env.example`
- Test: `backend/tests/test_alerts_config.py`

**Interfaces — Produces:**
- `app.models.Alert` with columns: `id, kind, subject_id, level, priority, title, reason, image_url, link, external_url, watch_keyword, scan_date, created_at, read_at, sent_at`.
- `app.analysis.alerts.AlertsConfig` (frozen dataclass: `niche_min_score: float = 60`, `niche_min_growth: float = 0.20`, `amazon_top_n: int = 20`, `cooldown_days: int = 7`, `telegram_max_items: int = 5`) and `load_alerts_config() -> AlertsConfig`.
- `Settings.telegram_bot_token: str | None`, `Settings.telegram_chat_id: str | None`, `Settings.app_url: str | None`.

- [ ] **Step 1: Write the failing test** — `backend/tests/test_alerts_config.py`

```python
from app.analysis import alerts as alerts_mod
from app.analysis.alerts import AlertsConfig, load_alerts_config
from app.config import Settings


def test_defaults_match_yaml():
    assert load_alerts_config() == AlertsConfig(
        niche_min_score=60, niche_min_growth=0.20, amazon_top_n=20, cooldown_days=7, telegram_max_items=5
    )


def test_missing_file_gives_defaults(monkeypatch):
    monkeypatch.setattr(alerts_mod, "load_yaml", lambda name: {})
    assert load_alerts_config() == AlertsConfig()


def test_telegram_settings_default_none():
    s = Settings(_env_file=None)
    assert s.telegram_bot_token is None and s.telegram_chat_id is None and s.app_url is None
```

- [ ] **Step 2: Run** `.venv/bin/pytest tests/test_alerts_config.py -q` → FAIL (ImportError).

- [ ] **Step 3: Implement**

`backend/config/alerts.yaml`:
```yaml
# Thông báo (Tin mới + Telegram) — kiểm tra sau mỗi lần quét. Chỉnh tự do.
niche_min_score: 60        # 🚀 ngách bứt phá: điểm tối thiểu
niche_min_growth: 0.20     # … và tăng trưởng > 20%
amazon_top_n: 20           # 🛒 sản phẩm mới lọt top N Best Sellers
cooldown_days: 7           # không báo lại cùng ngách/sản phẩm trong N ngày (trừ khi lên mức cao hơn)
telegram_max_items: 5      # số tin kèm ảnh mỗi lần quét; còn lại gom thành 1 dòng tóm tắt
```

`backend/app/analysis/alerts.py` (start of file):
```python
"""Alert rules: which niches/products are worth telling the user about after a scan."""

from dataclasses import dataclass, fields

from app.config_files import load_yaml


@dataclass(frozen=True)
class AlertsConfig:
    niche_min_score: float = 60
    niche_min_growth: float = 0.20
    amazon_top_n: int = 20
    cooldown_days: int = 7
    telegram_max_items: int = 5


def load_alerts_config() -> AlertsConfig:
    data = load_yaml("alerts.yaml")
    kwargs = {}
    for f in fields(AlertsConfig):
        if f.name in data:
            kwargs[f.name] = int(data[f.name]) if f.type in (int, "int") else float(data[f.name])
    return AlertsConfig(**kwargs)
```

`backend/app/models.py` — add `Index` to the `from sqlalchemy import (...)` list and append:
```python
class Alert(Base):
    """Something worth telling the user after a scan (Tin mới page + Telegram)."""

    __tablename__ = "alerts"
    __table_args__ = (Index("ix_alerts_kind_subject_created", "kind", "subject_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(20))  # niche | listing | hot_product | amazon
    subject_id: Mapped[int] = mapped_column(Integer)  # keyword id (niche) or product id
    level: Mapped[int] = mapped_column(Integer, default=1)
    priority: Mapped[float] = mapped_column(Float, default=0.0)  # higher = more important within a kind
    title: Mapped[str] = mapped_column(String(300))
    reason: Mapped[str] = mapped_column(String(300))
    image_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    link: Mapped[str] = mapped_column(String(300))  # in-app path
    external_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    watch_keyword: Mapped[str | None] = mapped_column(String(200), nullable=True)
    scan_date: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
```

`backend/app/config.py` — add to `Settings`:
```python
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    app_url: str | None = None  # e.g. http://<mac>.<tailnet>.ts.net:3737 — used for links in Telegram
```

`backend/.env.example` — append:
```
# Thông báo Telegram (chạy `make telegram-setup` để điền tự động)
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
# Địa chỉ mở app từ điện thoại (Tailscale), dùng cho link trong tin Telegram
APP_URL=
```
Note: empty env values must not break settings — if `TELEGRAM_BOT_TOKEN=` yields `""`, treat `""` as unset wherever used (`if not settings.telegram_bot_token`).

Migration: `cd backend && .venv/bin/alembic revision --autogenerate -m "alerts"`; open the file, keep only the `alerts` table + index create/drop; then `.venv/bin/alembic upgrade head`.

- [ ] **Step 4: Run** `.venv/bin/pytest -q` → all pass.
- [ ] **Step 5: Commit** `feat(alerts): alert model, migration and config`.

---

### Task 2: Pure alert rules + dedupe

**Files:**
- Modify: `backend/app/analysis/alerts.py`
- Test: `backend/tests/test_alerts_analysis.py`

**Interfaces — Consumes:** `AlertsConfig` (Task 1).
**Produces** (all in `app.analysis.alerts`):
```python
@dataclass(frozen=True)
class AlertCandidate:
    kind: str; subject_id: int; level: int; priority: float
    title: str; reason: str; image_url: str | None; link: str
    external_url: str | None; watch_keyword: str | None

@dataclass(frozen=True)
class NicheRow: keyword_id: int; text: str; score: float; growth: float | None; watch_keyword: str
@dataclass(frozen=True)
class ListingRow: product_id: int; title: str; url: str; image_url: str | None; status: str
    delta_saves: float | None; dsr: float | None; watch_keyword: str | None; link: str
@dataclass(frozen=True)
class HotRow: product_id: int; title: str; url: str; image_url: str | None
    velocity: float | None; metric: str | None; watch_keyword: str; link: str
@dataclass(frozen=True)
class AmazonRow: product_id: int; title: str; url: str; image_url: str | None
    category_key: str; rank: int; was_in_top: bool
@dataclass(frozen=True)
class PastAlert: kind: str; subject_id: int; level: int; created_at: datetime

def niche_candidates(rows: Iterable[NicheRow], cfg: AlertsConfig) -> list[AlertCandidate]
def listing_candidates(rows: Iterable[ListingRow]) -> list[AlertCandidate]
def hot_candidates(rows: Iterable[HotRow]) -> list[AlertCandidate]
def amazon_candidates(rows: Iterable[AmazonRow], cfg: AlertsConfig) -> list[AlertCandidate]
def dedupe(cands: Iterable[AlertCandidate], past: Iterable[PastAlert], now: datetime, cooldown_days: int) -> list[AlertCandidate]
def telegram_order(kind: str, level: int, priority: float) -> tuple[int, float]   # sort key, ascending
AMAZON_CATEGORY_LABEL: dict[str, str]
```

- [ ] **Step 1: Write failing tests** — `backend/tests/test_alerts_analysis.py`

```python
from datetime import datetime, timedelta

from app.analysis.alerts import (
    AlertsConfig, AmazonRow, HotRow, ListingRow, NicheRow, PastAlert,
    amazon_candidates, dedupe, hot_candidates, listing_candidates, niche_candidates, telegram_order,
)

CFG = AlertsConfig()
NOW = datetime(2026, 10, 8, 13, 0)


def test_niche_needs_score_and_growth():
    rows = [
        NicheRow(1, "football mom game day", 64, 0.35, "football mom"),
        NicheRow(2, "low score", 59.9, 0.9, "football mom"),
        NicheRow(3, "flat", 80, 0.20, "football mom"),   # growth must be > 20%
        NicheRow(4, "no growth", 80, None, "football mom"),
    ]
    out = niche_candidates(rows, CFG)
    assert [c.subject_id for c in out] == [1]
    c = out[0]
    assert (c.kind, c.level, c.link, c.watch_keyword) == ("niche", 1, "/trends/1", "football mom")
    assert c.reason == "Điểm 64 · tăng 35%"
    assert c.priority == 64


def test_listing_levels_and_scope():
    base = dict(title="t", url="u", image_url="i", delta_saves=12.4, dsr=0.18, link="/signals")
    rows = [
        ListingRow(10, status="super_breakout", watch_keyword=None, **base),   # global
        ListingRow(11, status="steady_grower", watch_keyword="pickleball", **base),
        ListingRow(12, status="steady_grower", watch_keyword=None, **base),    # out of scope
        ListingRow(13, status="calibrating", watch_keyword="pickleball", **base),
    ]
    out = {c.subject_id: c for c in listing_candidates(rows)}
    assert set(out) == {10, 11}
    assert out[10].level == 2 and out[11].level == 1
    assert out[10].reason == "Super Breakout · +12 lượt lưu/ngày · DSR 18%"
    assert out[11].reason == "Steady Grower · +12 lượt lưu/ngày · DSR 18%"
    assert out[10].priority == 12.4


def test_listing_reason_handles_missing_numbers():
    row = ListingRow(1, "t", "u", None, "super_breakout", None, None, None, "/signals")
    assert listing_candidates([row])[0].reason == "Super Breakout"


def test_hot_reason():
    out = hot_candidates([HotRow(5, "t", "u", "i", 3.5, "reviews", "game day", "/products?keyword_id=9")])
    assert out[0].kind == "hot_product" and out[0].reason == "Đang bán chạy · +3.5 reviews/tuần"
    assert out[0].link == "/products?keyword_id=9"


def test_amazon_new_into_top():
    rows = [
        AmazonRow(7, "t", "u", "i", "women_tshirts", 7, was_in_top=False),
        AmazonRow(8, "t", "u", "i", "women_tshirts", 3, was_in_top=True),
        AmazonRow(9, "t", "u", "i", "men_hoodies", 21, was_in_top=False),
    ]
    out = amazon_candidates(rows, CFG)
    assert [c.subject_id for c in out] == [7]
    assert out[0].reason == "Hạng 7 · Áo thun nữ · Best Sellers"
    assert out[0].link == "/amazon?category=women_tshirts"
    assert out[0].priority == -7


def _cand(kind="listing", sid=1, level=1):
    return listing_candidates([ListingRow(sid, "t", "u", None,
        "super_breakout" if level == 2 else "steady_grower", 1, 0.1, "k", "/s")])[0] if kind == "listing" else None


def test_dedupe_cooldown_and_escalation():
    past = [
        PastAlert("listing", 1, 1, NOW - timedelta(days=2)),   # recent L1
        PastAlert("listing", 2, 1, NOW - timedelta(days=8)),   # expired
        PastAlert("listing", 3, 2, NOW - timedelta(days=1)),   # recent L2
    ]
    cands = [_cand(sid=1, level=1), _cand(sid=1, level=2), _cand(sid=2), _cand(sid=3, level=2)]
    out = dedupe(cands, past, NOW, 7)
    assert [(c.subject_id, c.level) for c in out] == [(1, 2), (2, 1)]


def test_dedupe_same_subject_twice_in_one_run():
    out = dedupe([_cand(sid=4), _cand(sid=4)], [], NOW, 7)
    assert len(out) == 1


def test_telegram_order():
    keys = sorted([
        ("hot_product", 1, 9.0), ("listing", 1, 5.0), ("amazon", 1, -3.0),
        ("niche", 1, 70.0), ("listing", 2, 1.0),
    ], key=lambda k: telegram_order(*k))
    assert [k[0] for k in keys] == ["listing", "niche", "amazon", "listing", "hot_product"]
    assert keys[0][1] == 2
```

- [ ] **Step 2: Run** `.venv/bin/pytest tests/test_alerts_analysis.py -q` → FAIL (ImportError).

- [ ] **Step 3: Implement** — append to `backend/app/analysis/alerts.py` (add imports `from collections.abc import Iterable`, `from datetime import datetime, timedelta`):

```python
AMAZON_CATEGORY_LABEL = {
    "women_tshirts": "Áo thun nữ", "men_tshirts": "Áo thun nam", "women_hoodies": "Hoodie nữ",
    "women_sweatshirts": "Sweatshirt nữ", "men_hoodies": "Hoodie nam", "men_sweatshirts": "Sweatshirt nam",
    "boys_tops": "Áo bé trai", "girls_tops": "Áo bé gái",
}
LISTING_LABEL = {"super_breakout": "Super Breakout", "steady_grower": "Steady Grower"}
METRIC_LABEL = {"reviews": "reviews", "favorites": "lượt lưu", "views": "lượt xem"}
# Telegram order: super breakout, niche, amazon, steady grower, hot product
KIND_RANK = {("listing", 2): 0, ("niche", 1): 1, ("amazon", 1): 2, ("listing", 1): 3, ("hot_product", 1): 4}


@dataclass(frozen=True)
class AlertCandidate:
    kind: str
    subject_id: int
    level: int
    priority: float
    title: str
    reason: str
    image_url: str | None
    link: str
    external_url: str | None
    watch_keyword: str | None


@dataclass(frozen=True)
class NicheRow:
    keyword_id: int
    text: str
    score: float
    growth: float | None
    watch_keyword: str


@dataclass(frozen=True)
class ListingRow:
    product_id: int
    title: str
    url: str
    image_url: str | None
    status: str
    delta_saves: float | None
    dsr: float | None
    watch_keyword: str | None
    link: str


@dataclass(frozen=True)
class HotRow:
    product_id: int
    title: str
    url: str
    image_url: str | None
    velocity: float | None
    metric: str | None
    watch_keyword: str
    link: str


@dataclass(frozen=True)
class AmazonRow:
    product_id: int
    title: str
    url: str
    image_url: str | None
    category_key: str
    rank: int
    was_in_top: bool


@dataclass(frozen=True)
class PastAlert:
    kind: str
    subject_id: int
    level: int
    created_at: datetime


def niche_candidates(rows: Iterable[NicheRow], cfg: AlertsConfig) -> list[AlertCandidate]:
    return [
        AlertCandidate(
            kind="niche", subject_id=r.keyword_id, level=1, priority=r.score, title=r.text,
            reason=f"Điểm {r.score:.0f} · tăng {r.growth * 100:.0f}%", image_url=None,
            link=f"/trends/{r.keyword_id}", external_url=None, watch_keyword=r.watch_keyword,
        )
        for r in rows
        if r.score >= cfg.niche_min_score and r.growth is not None and r.growth > cfg.niche_min_growth
    ]


def listing_candidates(rows: Iterable[ListingRow]) -> list[AlertCandidate]:
    out = []
    for r in rows:
        if r.status == "super_breakout":
            level = 2
        elif r.status == "steady_grower" and r.watch_keyword is not None:
            level = 1
        else:
            continue
        parts = [LISTING_LABEL[r.status]]
        if r.delta_saves is not None:
            parts.append(f"+{r.delta_saves:.0f} lượt lưu/ngày")
        if r.dsr is not None:
            parts.append(f"DSR {r.dsr * 100:.0f}%")
        out.append(AlertCandidate(
            kind="listing", subject_id=r.product_id, level=level, priority=r.delta_saves or 0.0,
            title=r.title, reason=" · ".join(parts), image_url=r.image_url, link=r.link,
            external_url=r.url, watch_keyword=r.watch_keyword,
        ))
    return out


def hot_candidates(rows: Iterable[HotRow]) -> list[AlertCandidate]:
    out = []
    for r in rows:
        reason = "Đang bán chạy"
        if r.velocity is not None and r.metric:
            reason += f" · +{r.velocity:.1f} {METRIC_LABEL.get(r.metric, r.metric)}/tuần"
        out.append(AlertCandidate(
            kind="hot_product", subject_id=r.product_id, level=1, priority=r.velocity or 0.0,
            title=r.title, reason=reason, image_url=r.image_url, link=r.link,
            external_url=r.url, watch_keyword=r.watch_keyword,
        ))
    return out


def amazon_candidates(rows: Iterable[AmazonRow], cfg: AlertsConfig) -> list[AlertCandidate]:
    return [
        AlertCandidate(
            kind="amazon", subject_id=r.product_id, level=1, priority=-float(r.rank), title=r.title,
            reason=f"Hạng {r.rank} · {AMAZON_CATEGORY_LABEL.get(r.category_key, r.category_key)} · Best Sellers",
            image_url=r.image_url, link=f"/amazon?category={r.category_key}",
            external_url=r.url, watch_keyword=None,
        )
        for r in rows
        if r.rank <= cfg.amazon_top_n and not r.was_in_top
    ]


def dedupe(
    cands: Iterable[AlertCandidate], past: Iterable[PastAlert], now: datetime, cooldown_days: int
) -> list[AlertCandidate]:
    """Drop candidates alerted within the cooldown unless the level rose; one per (kind, subject)."""
    cutoff = now - timedelta(days=cooldown_days)
    recent: dict[tuple[str, int], int] = {}
    for p in past:
        if p.created_at >= cutoff:
            key = (p.kind, p.subject_id)
            recent[key] = max(recent.get(key, 0), p.level)
    best: dict[tuple[str, int], AlertCandidate] = {}
    for c in cands:
        key = (c.kind, c.subject_id)
        if key in recent and c.level <= recent[key]:
            continue
        if key not in best or c.level > best[key].level:
            best[key] = c
    return list(best.values())


def telegram_order(kind: str, level: int, priority: float) -> tuple[int, float]:
    return (KIND_RANK.get((kind, level), 9), -priority)
```

Note `dedupe` keeps insertion order of first occurrence per key (dict order); test expects `[(1, 2), (2, 1)]` — subject 1's L1 is dropped (recent L1), its L2 kept.

- [ ] **Step 4: Run** `.venv/bin/pytest tests/test_alerts_analysis.py -q` → PASS; then full suite.
- [ ] **Step 5: Commit** `feat(alerts): alert rules and dedupe`.

---

### Task 3: Watchlist helpers, shared hot computation, Signals keyword filter

**Files:**
- Create: `backend/app/services/watchlist.py`
- Create: `backend/app/services/hot.py`
- Modify: `backend/app/api/products.py` (use `compute_product_metrics`)
- Modify: `backend/app/api/signals.py` (add `keyword` query param)
- Test: `backend/tests/test_watchlist_service.py`, extend `backend/tests/test_api_signals.py`

**Interfaces — Produces:**
```python
# app/services/watchlist.py
def watch_keywords(session) -> list[Seed]                       # active seeds ordered by id
def listing_keyword_filter(keyword: str, suffix: str) -> ColumnElement[bool]
    # SQL: ListingSignal.discovery_query == f"{kw} {suffix}"  OR  lower(Product.title) LIKE %kw%
    # (kw = normalize_keyword(keyword); escape % and _ ; requires Product joined)
def listing_matches(keyword: str, discovery_query: str, title: str, suffix: str) -> bool  # same rule in Python
def child_keyword_ids(session, seed_text: str) -> list[int]    # children of the seed keyword (normalized + canonical forms) via KeywordRelation

# app/services/hot.py
@dataclass(frozen=True)
class ProductMetrics: delta_7d: float | None; velocity: float | None; metric: str | None; hot: bool
def compute_product_metrics(session) -> tuple[list[Product], dict[int, ProductMetrics]]
    # same product population and hot rule as GET /api/products today
```

- [ ] **Step 1: Write failing tests** — `backend/tests/test_watchlist_service.py`

```python
from datetime import date

from sqlalchemy import select

from app.keywords import get_or_create_keyword
from app.models import KeywordRelation, ListingSignal, Product, Seed
from app.services.watchlist import child_keyword_ids, listing_keyword_filter, listing_matches, watch_keywords


def _listing(session, pid, title, query):
    p = Product(source="etsy", external_id=str(pid), title=title, url="u", product_type="tshirt")
    session.add(p)
    session.flush()
    session.add(ListingSignal(product_id=p.id, discovered_on=date(2026, 10, 1), discovery_query=query))
    return p


def test_listing_matches():
    assert listing_matches("Pickleball", "pickleball shirt", "x", "shirt")
    assert listing_matches("pickleball", "graphic tee", "Funny PICKLEBALL Tee", "shirt")
    assert not listing_matches("pickleball", "graphic tee", "tennis tee", "shirt")


def test_listing_keyword_filter_sql(session):
    a = _listing(session, 1, "Funny Pickleball Tee", "graphic tee")
    b = _listing(session, 2, "Anything", "pickleball shirt")
    _listing(session, 3, "Tennis 100% tee", "graphic tee")
    session.flush()
    ids = session.scalars(
        select(Product.id).join(ListingSignal, ListingSignal.product_id == Product.id)
        .where(listing_keyword_filter("pickleball", "shirt"))
    ).all()
    assert sorted(ids) == sorted([a.id, b.id])
    # LIKE wildcards in the keyword are literal
    assert session.scalars(
        select(Product.id).join(ListingSignal, ListingSignal.product_id == Product.id)
        .where(listing_keyword_filter("100%", "shirt"))
    ).all() == [3]


def test_watch_keywords_and_children(session):
    session.add_all([Seed(keyword="game day"), Seed(keyword="old", active=False)])
    parent = get_or_create_keyword(session, "game day")
    child = get_or_create_keyword(session, "game day vibes", origin="discovered", has_parent=True)
    session.add(KeywordRelation(parent_id=parent.id, child_id=child.id, source="etsy", last_seen=date(2026, 10, 7)))
    session.flush()
    assert [s.keyword for s in watch_keywords(session)] == ["game day"]
    assert child_keyword_ids(session, "game day") == [child.id]
```

Signals API test (add to the existing signals API test file, reusing its helpers for creating listings; if none exist, create products + `ListingSignal(updated_on=..., status="steady_grower")` directly):
```python
def test_signals_keyword_filter(client, session):
    # two steady_grower listings updated today: one titled "Pickleball Queen Tee", one "Dog Tee"
    ...
    r = client.get("/api/signals", params={"keyword": "pickleball", "status": "all"})
    assert [i["title"] for i in r.json()["items"]] == ["Pickleball Queen Tee"]
    assert r.json()["total"] == 1
```
(Write it concretely using the same fixtures/helpers as the neighbouring tests.)

Products regression: existing `tests/test_products*.py` must still pass unchanged.

- [ ] **Step 2: Run** the new tests → FAIL.

- [ ] **Step 3: Implement**

`backend/app/services/watchlist.py`:
```python
"""Watchlist (seed keywords) helpers shared by the Watchlist page, Signals filter and alerts."""

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.orm import Session

from app.keywords import canonical_keyword, normalize_keyword
from app.models import Keyword, KeywordRelation, ListingSignal, Product, Seed


def watch_keywords(session: Session) -> list[Seed]:
    return list(session.scalars(select(Seed).where(Seed.active.is_(True)).order_by(Seed.id)))


def _like_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def listing_keyword_filter(keyword: str, suffix: str) -> ColumnElement[bool]:
    """Listing found by '<keyword> <suffix>' or whose title contains the keyword (case-insensitive)."""
    kw = normalize_keyword(keyword)
    return or_(
        ListingSignal.discovery_query == f"{kw} {suffix}",
        func.lower(Product.title).like(f"%{_like_escape(kw)}%", escape="\\"),
    )


def listing_matches(keyword: str, discovery_query: str, title: str, suffix: str) -> bool:
    kw = normalize_keyword(keyword)
    return discovery_query == f"{kw} {suffix}" or kw in title.lower()


def child_keyword_ids(session: Session, seed_text: str) -> list[int]:
    texts = {normalize_keyword(seed_text), canonical_keyword(seed_text)}
    parent_ids = list(session.scalars(select(Keyword.id).where(Keyword.text.in_(texts))))
    if not parent_ids:
        return []
    return sorted(set(session.scalars(
        select(KeywordRelation.child_id).where(KeywordRelation.parent_id.in_(parent_ids))
    )))
```

`backend/app/services/hot.py` — move the population + metrics + hot logic out of `api/products.py::list_products`:
```python
"""Velocity and 🔥 hot flags for Best Sellers products (shared by the products API and alerts)."""

from dataclasses import dataclass

from sqlalchemy import exists, select
from sqlalchemy.orm import Session, selectinload

from app.analysis.velocity import SnapshotPoint, compute_velocity, hot_ids, velocity_metric
from app.models import ListingSignal, Product, ProductKeyword


@dataclass(frozen=True)
class ProductMetrics:
    delta_7d: float | None
    velocity: float | None
    metric: str | None
    hot: bool


def compute_product_metrics(session: Session) -> tuple[list[Product], dict[int, ProductMetrics]]:
    """Best Sellers population: products not only tracked by Listing Signals, or linked to a keyword."""
    products = list(session.scalars(
        select(Product)
        .where(
            ~exists().where(ListingSignal.product_id == Product.id)
            | exists().where(ProductKeyword.product_id == Product.id)
        )
        .order_by(Product.id)
        .options(selectinload(Product.snapshots))
    ))
    points = {
        p.id: [SnapshotPoint(s.date, s.reviews, s.favorites, s.views) for s in p.snapshots] for p in products
    }
    velocities = {
        p.id: compute_velocity(points[p.id], p.listed_at.date() if p.listed_at else None) for p in products
    }
    hot = hot_ids((p.id, (p.source, p.product_type), velocities[p.id][1]) for p in products if not p.licensed)
    return products, {
        p.id: ProductMetrics(velocities[p.id][0], velocities[p.id][1], velocity_metric(points[p.id]), p.id in hot)
        for p in products
    }
```
Then in `api/products.py::list_products` replace the inline select/points/metrics/hot block with `products, metrics = compute_product_metrics(session)` and adapt `_to_out(p, metrics[p.id], keywords)` to read `m.delta_7d`, `m.velocity`, `m.metric`, `m.hot`. Remove now-unused imports. Response must be byte-for-byte the same.

`backend/app/api/signals.py` — add param `keyword: str | None = None`; when set, `filters.append(listing_keyword_filter(keyword, load_signals_config().seed_query_suffix))`. The `total` count query must join `Product` too when the filter is used: change it to `select(func.count()).select_from(ListingSignal).join(Product, Product.id == ListingSignal.product_id).where(*filters)`. Leave the `counts` (tab badge) query with the keyword filter applied as well so tab counts reflect the chosen keyword: also join Product there and include the keyword filter in its where clause.

- [ ] **Step 4: Run** full suite `.venv/bin/pytest -q` → PASS.
- [ ] **Step 5: Commit** `feat(watchlist): keyword helpers, shared hot metrics, signals keyword filter`.

---

### Task 4: Detect alerts after each scan

**Files:**
- Create: `backend/app/services/alerts.py`
- Modify: `backend/app/pipeline/scan.py` (call detection after rescore)
- Test: `backend/tests/test_alerts_service.py`

**Interfaces — Consumes:** Task 2 rules, Task 3 `watch_keywords`, `child_keyword_ids`, `listing_matches`, `compute_product_metrics`, `load_signals_config`.
**Produces:** `detect_alerts(session: Session, today: date, cfg: AlertsConfig | None = None, now: datetime | None = None) -> list[Alert]` (inserts + flushes; caller commits).

Data loading rules (implement exactly):
- **Niche rows:** for each watch seed `s`: keyword ids = seed keyword (`Keyword.text == normalize_keyword(s.keyword)`, plus canonical form) + `child_keyword_ids`. Take each id's `KeywordScore` on the latest score date (`max(KeywordScore.date)`), only `Keyword.is_pod_relevant`. `watch_keyword = s.keyword`. First seed wins if a keyword appears under two seeds.
- **Listing rows:** `ListingSignal` with `updated_on == max(updated_on)` and status in (`super_breakout`, `steady_grower`), joined to `Product`. `watch_keyword` = first watch seed for which `listing_matches(seed, sig.discovery_query, p.title, suffix)` is true, else None. `link` = `/signals?keyword=<urlencoded seed>&status=all` when matched, else `/signals?status=super_breakout`.
- **Hot rows:** `products, metrics = compute_product_metrics(session)`; product hot and linked via `ProductKeyword` to a watch seed's keyword id → `HotRow(..., velocity=m.velocity, metric=m.metric, watch_keyword=seed, link=f"/products?keyword_id={seed_keyword_id}")`.
- **Amazon rows:** latest `AmazonRank.date` for `list_name == "bestsellers"`; previous date = max date `<` latest for bestsellers. For each rank row on latest date with `rank <= cfg.amazon_top_n` whose product is not `licensed`: `was_in_top` = exists a row same product, same category, previous date, rank `<= amazon_top_n`. If there is no previous date, produce **no** Amazon rows (first scan would otherwise flag the whole top 20).
- Past alerts: all `Alert` rows with `created_at >= now - cooldown_days` → `PastAlert`.
- Insert one `Alert` per deduped candidate with `scan_date=today`, `created_at=now`.

`scan.py` — after the rescore try/except block, add:
```python
    try:
        with session_factory() as session:
            detect_alerts(session, today)
            session.commit()
    except Exception:  # alerts must never break a scan
        logger.exception("Alert detection failed")
```
(import `from app.services.alerts import detect_alerts` at top; check for circular imports — if any, import inside the function.)

- [ ] **Step 1: Write failing tests** — `backend/tests/test_alerts_service.py`

```python
from datetime import date, datetime

from sqlalchemy import select

from app.analysis.alerts import AlertsConfig
from app.keywords import get_or_create_keyword
from app.models import (
    Alert, AmazonRank, KeywordRelation, KeywordScore, ListingSignal, Product, Seed,
)
from app.services.alerts import detect_alerts

TODAY = date(2026, 10, 8)
NOW = datetime(2026, 10, 8, 13, 0)


def _product(session, ext, title, source="etsy", licensed=False):
    p = Product(source=source, external_id=ext, title=title, url=f"https://x/{ext}",
                image_url=f"https://img/{ext}.jpg", product_type="tshirt", licensed=licensed)
    session.add(p)
    session.flush()
    return p


def test_detects_niche_listing_and_amazon(session):
    session.add(Seed(keyword="game day"))
    seed_kw = get_or_create_keyword(session, "game day")
    child = get_or_create_keyword(session, "game day vibes", origin="discovered", has_parent=True)
    session.add(KeywordRelation(parent_id=seed_kw.id, child_id=child.id, source="etsy", last_seen=TODAY))
    session.add(KeywordScore(keyword_id=child.id, score=70, growth=0.5, date=TODAY))
    session.add(KeywordScore(keyword_id=seed_kw.id, score=40, growth=0.5, date=TODAY))

    lp = _product(session, "l1", "Game Day Vibes Tee")
    session.add(ListingSignal(product_id=lp.id, discovered_on=TODAY, discovery_query="graphic tee",
                              status="steady_grower", delta_saves=6, dsr=0.1, updated_on=TODAY))
    other = _product(session, "l2", "Cat Tee")
    session.add(ListingSignal(product_id=other.id, discovered_on=TODAY, discovery_query="graphic tee",
                              status="steady_grower", delta_saves=9, dsr=0.1, updated_on=TODAY))

    a_new = _product(session, "a1", "Funny Tee", source="amazon")
    a_old = _product(session, "a2", "Old Tee", source="amazon")
    a_lic = _product(session, "a3", "NFL Tee", source="amazon", licensed=True)
    prev = date(2026, 10, 7)
    session.add_all([
        AmazonRank(product_id=a_old.id, date=prev, category_key="women_tshirts", list_name="bestsellers", rank=5),
        AmazonRank(product_id=a_new.id, date=prev, category_key="women_tshirts", list_name="bestsellers", rank=40),
        AmazonRank(product_id=a_old.id, date=TODAY, category_key="women_tshirts", list_name="bestsellers", rank=4),
        AmazonRank(product_id=a_new.id, date=TODAY, category_key="women_tshirts", list_name="bestsellers", rank=9),
        AmazonRank(product_id=a_lic.id, date=TODAY, category_key="women_tshirts", list_name="bestsellers", rank=1),
    ])
    session.flush()

    alerts = detect_alerts(session, TODAY, AlertsConfig(), NOW)
    got = sorted((a.kind, a.subject_id) for a in alerts)
    assert got == sorted([("niche", child.id), ("listing", lp.id), ("amazon", a_new.id)])
    listing = next(a for a in alerts if a.kind == "listing")
    assert listing.watch_keyword == "game day"
    assert listing.link == "/signals?keyword=game+day&status=all"


def test_second_run_is_deduped(session):
    p = _product(session, "s1", "Anything")
    session.add(ListingSignal(product_id=p.id, discovered_on=TODAY, discovery_query="shirt",
                              status="super_breakout", delta_saves=20, dsr=0.3, updated_on=TODAY))
    session.flush()
    assert len(detect_alerts(session, TODAY, AlertsConfig(), NOW)) == 1
    assert detect_alerts(session, TODAY, AlertsConfig(), NOW) == []
    assert session.scalar(select(Alert.link)) == "/signals?status=super_breakout"


def test_no_amazon_alerts_without_previous_day(session):
    a = _product(session, "a9", "Tee", source="amazon")
    session.add(AmazonRank(product_id=a.id, date=TODAY, category_key="men_tshirts", list_name="bestsellers", rank=1))
    session.flush()
    assert detect_alerts(session, TODAY, AlertsConfig(), NOW) == []


async def test_run_scan_survives_alert_failure(session_factory, monkeypatch):
    from app.pipeline import scan as scan_mod
    from tests.fakes import FakeConnector

    def boom(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(scan_mod, "detect_alerts", boom)
    run_ids = await scan_mod.run_scan(session_factory, [FakeConnector()])
    assert len(run_ids) == 1
```

- [ ] **Step 2: Run** → FAIL. **Step 3:** implement `app/services/alerts.py` per the loading rules (use `urllib.parse.urlencode({"keyword": seed, "status": "all"})` for the link). **Step 4:** full suite PASS.
- [ ] **Step 5: Commit** `feat(alerts): detect alerts after each scan`.

---

### Task 5: Telegram delivery + setup command

**Files:**
- Create: `backend/app/notify/__init__.py` (empty), `backend/app/notify/telegram.py`
- Create: `backend/scripts/telegram_setup.py`
- Modify: `backend/app/pipeline/scan.py` (send after detection), `Makefile` (`telegram-setup` target, add to `.PHONY`)
- Test: `backend/tests/test_telegram.py`

**Interfaces — Consumes:** `Alert`, `AlertsConfig`, `telegram_order`, `Settings.telegram_bot_token/telegram_chat_id/app_url`.
**Produces:**
```python
API = "https://api.telegram.org"
def telegram_configured(settings: Settings) -> bool
async def send_pending(session: Session, settings: Settings, cfg: AlertsConfig | None = None,
                       *, client: httpx.AsyncClient | None = None, now: datetime | None = None) -> int  # alerts marked sent
async def send_text(settings: Settings, text: str, *, client: httpx.AsyncClient | None = None) -> None  # raises TelegramError
class TelegramError(Exception)  # message never contains the token
def format_caption(alert: Alert, app_url: str | None) -> str     # HTML
```

Behaviour:
- Not configured (token or chat id empty/None) → return 0, no HTTP.
- Pending = `Alert.sent_at IS NULL` and `created_at >= now - 2 days`. Sort by `telegram_order(kind, level, priority)`.
- First `cfg.telegram_max_items` → `sendPhoto` (`chat_id`, `photo=image_url`, `caption`, `parse_mode=HTML`) or `sendMessage` (`text`, `parse_mode=HTML`, `disable_web_page_preview=true`) when `image_url` is None. If `sendPhoto` returns 400 (bad image URL), retry that alert once as `sendMessage`.
- If more remain: one `sendMessage`: `f"… và {n} tin khác — xem trong app: {app_url}/alerts"` (without the link part when `app_url` empty).
- Mark sent (`sent_at=now`) every alert that was delivered, and all summarized ones once the summary is delivered. On HTTP 429 → stop immediately, keep the rest unsent. On other HTTP errors / `httpx.HTTPError` for an item → log `logger.warning("Telegram send failed: %s", status_or_exc_class)` (never the URL — it contains the token) and continue with the next item.
- Caption format (HTML-escape title/reason with `html.escape`):
```
{icon} <b>{KIND_TITLE}</b>{" · " + watch_keyword if watch_keyword}
{title}
{reason}
<a href="{app_url}{link}">Mở trong app</a>{" · " + <a href="{external_url}">Etsy/Amazon</a> if external_url}
```
  icons/titles: niche 🚀 "Ngách bứt phá"; listing 🔥 "Etsy bứt phá"; hot_product ⭐ "Sản phẩm hot"; amazon 🛒 "Amazon mới vào top". External label: "Amazon" if `"amazon." in external_url` else "Etsy". Omit the app link when `app_url` is empty. Truncate caption to 1024 chars.

`scan.py` — after the detection block:
```python
    try:
        with session_factory() as session:
            await send_pending(session, get_settings())
            session.commit()
    except Exception:
        logger.exception("Telegram delivery failed")
```
`run_scan` has no settings parameter; use `app.config.get_settings()` (cached). In tests, settings come from env → unconfigured → no HTTP.

`scripts/telegram_setup.py` (interactive; not unit-tested):
1. `getpass("Bot token (từ @BotFather): ")`.
2. GET `/bot{token}/getMe` → print bot username; on failure print "Token không đúng" and exit 1.
3. GET `/bot{token}/getUpdates` → chat id of the latest `message.chat` with `type == "private"`; if none print "Hãy mở Telegram, gửi 1 tin bất kỳ cho bot @{username} rồi chạy lại." exit 1.
4. Ask for APP_URL with default from `tailscale status --json` (`Self.DNSName` stripped of the trailing dot → `http://{name}:3737`); empty input keeps the default.
5. Update/append `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `APP_URL` lines in `backend/.env` (preserve other lines; replace existing keys in place).
6. Send "✅ POD Trend Radar đã kết nối. Bạn sẽ nhận tin sau mỗi lần quét (8:00 và 20:00)." and print "Đã lưu vào backend/.env và gửi tin thử." Never print the token.

Makefile:
```make
telegram-setup:
	cd backend && .venv/bin/python scripts/telegram_setup.py
```

- [ ] **Step 1: Write failing tests** — `backend/tests/test_telegram.py` (respx; mirror the respx usage in existing connector tests)

```python
from datetime import datetime, timedelta

import httpx
import pytest
import respx

from app.config import Settings
from app.analysis.alerts import AlertsConfig
from app.models import Alert
from app.notify.telegram import format_caption, send_pending

NOW = datetime(2026, 10, 8, 13, 0)
TOKEN = "123:secret"
BASE = f"https://api.telegram.org/bot{TOKEN}"


def _settings(**kw):
    return Settings(_env_file=None, telegram_bot_token=TOKEN, telegram_chat_id="42",
                    app_url="http://mac.ts.net:3737", **kw)


def _alert(session, i, kind="listing", level=1, priority=1.0, image=True, created=NOW):
    a = Alert(kind=kind, subject_id=i, level=level, priority=priority, title=f"Tee <{i}>", reason="+5 lượt lưu/ngày",
              image_url=f"https://img/{i}.jpg" if image else None, link=f"/signals?x={i}",
              external_url=f"https://www.etsy.com/listing/{i}", watch_keyword="game day",
              scan_date=NOW.date(), created_at=created)
    session.add(a)
    session.flush()
    return a


def test_caption():
    a = Alert(kind="listing", subject_id=1, level=2, priority=1, title="A & B", reason="Super Breakout",
              image_url=None, link="/signals", external_url="https://www.etsy.com/listing/1",
              watch_keyword="pickleball", scan_date=NOW.date())
    text = format_caption(a, "http://mac:3737")
    assert text.startswith("🔥 <b>Etsy bứt phá</b> · pickleball\nA &amp; B\nSuper Breakout\n")
    assert '<a href="http://mac:3737/signals">Mở trong app</a>' in text
    assert '<a href="https://www.etsy.com/listing/1">Etsy</a>' in text


async def test_not_configured_sends_nothing(session):
    _alert(session, 1)
    with respx.mock(assert_all_called=False) as mock:
        n = await send_pending(session, Settings(_env_file=None), now=NOW)
    assert n == 0 and not mock.calls


async def test_sends_top_items_and_summary(session):
    for i in range(7):
        _alert(session, i, priority=float(i))
    _alert(session, 99, created=NOW - timedelta(days=3))  # too old, ignored
    with respx.mock() as mock:
        photo = mock.post(f"{BASE}/sendPhoto").mock(return_value=httpx.Response(200, json={"ok": True}))
        msg = mock.post(f"{BASE}/sendMessage").mock(return_value=httpx.Response(200, json={"ok": True}))
        n = await send_pending(session, _settings(), AlertsConfig(telegram_max_items=5), now=NOW)
    assert n == 7
    assert photo.call_count == 5 and msg.call_count == 1
    assert "và 2 tin khác" in msg.calls[0].request.content.decode()
    assert all(a.sent_at is not None for a in session.query(Alert).filter(Alert.subject_id < 99))


async def test_failure_keeps_unsent_and_429_stops(session, caplog):
    _alert(session, 1, priority=3)
    _alert(session, 2, priority=2)
    _alert(session, 3, priority=1)
    with respx.mock() as mock:
        mock.post(f"{BASE}/sendPhoto").mock(side_effect=[
            httpx.Response(500), httpx.Response(429), httpx.Response(200, json={"ok": True}),
        ])
        n = await send_pending(session, _settings(), now=NOW)
    assert n == 0
    assert all(a.sent_at is None for a in session.query(Alert))
    assert TOKEN not in caplog.text


async def test_bad_photo_falls_back_to_text(session):
    _alert(session, 1)
    with respx.mock() as mock:
        mock.post(f"{BASE}/sendPhoto").mock(return_value=httpx.Response(400))
        msg = mock.post(f"{BASE}/sendMessage").mock(return_value=httpx.Response(200, json={"ok": True}))
        n = await send_pending(session, _settings(), now=NOW)
    assert n == 1 and msg.call_count == 1
```

- [ ] **Step 2: Run** → FAIL. **Step 3:** implement. Use `httpx.AsyncClient(timeout=20)` when no client is passed; send form/json bodies (`json=` is fine). **Step 4:** full suite PASS.
- [ ] **Step 5: Commit** `feat(alerts): Telegram delivery and make telegram-setup`.

---

### Task 6: Alerts and Watchlist APIs

**Files:**
- Create: `backend/app/api/alerts.py`, `backend/app/api/watchlist.py`
- Modify: `backend/app/api/schemas.py`, `backend/app/main.py` (register routers)
- Test: `backend/tests/test_alerts_api.py`, `backend/tests/test_watchlist_api.py`

**Interfaces — Produces (JSON):**
```
GET  /api/alerts?limit=100   → {"unread": int, "items": [AlertOut]}   newest first (created_at desc, id desc)
     AlertOut = {id, kind, level, title, reason, image_url, link, external_url, watch_keyword,
                 scan_date, created_at, read: bool}
GET  /api/alerts/unread-count → {"unread": int}
POST /api/alerts/read         → {"unread": 0}   (sets read_at=now on all unread)
GET  /api/alerts/telegram     → {"configured": bool, "app_url": str | null}
POST /api/alerts/test         → 200 {"ok": true} | 400 {"detail": "Chưa cấu hình Telegram — chạy make telegram-setup"} | 502 {"detail": "Telegram từ chối: <status>"}
GET  /api/watchlist           → {"date": str|null, "items": [WatchItem]}
     WatchItem = {seed_id, keyword, keyword_id, score: float|null, growth: float|null,
                  children_total: int, children: [{keyword_id, keyword, score}] (top 3 by score, pod-relevant only),
                  listings: {"super_breakout": int, "steady_grower": int},
                  thumbnails: [{product_id, image_url, title, url, status}] (≤4, super_breakout first, then by delta_saves desc),
                  alerts_7d: int}
```
`/api/alerts/test` uses `send_text(settings, "🔔 Tin thử từ POD Trend Radar")`. Settings come from `request.app.state.settings`. Watchlist listing counts/thumbnails use listings on the latest `updated_on` matched with `listing_keyword_filter(seed, suffix)`. `alerts_7d` counts `Alert.watch_keyword == seed.keyword` in the last 7 days. Children use `child_keyword_ids` + latest `KeywordScore`.

- [ ] **Step 1: Write failing tests**

`backend/tests/test_alerts_api.py`:
```python
from datetime import date, datetime

from app.models import Alert


def _add(session, i, read=False):
    session.add(Alert(kind="niche", subject_id=i, level=1, priority=60, title=f"n{i}", reason="Điểm 60",
                      link=f"/trends/{i}", scan_date=date(2026, 10, 8),
                      created_at=datetime(2026, 10, 8, 1, i), read_at=datetime(2026, 10, 8) if read else None))
    session.commit()


def test_list_and_mark_read(client, session):
    _add(session, 1, read=True)
    _add(session, 2)
    r = client.get("/api/alerts").json()
    assert r["unread"] == 1 and [i["title"] for i in r["items"]] == ["n2", "n1"]
    assert r["items"][0]["read"] is False
    assert client.get("/api/alerts/unread-count").json() == {"unread": 1}
    assert client.post("/api/alerts/read").json() == {"unread": 0}
    assert client.get("/api/alerts/unread-count").json() == {"unread": 0}


def test_telegram_status_has_no_secret(client):
    body = client.get("/api/alerts/telegram").json()
    assert body == {"configured": False, "app_url": None}


def test_test_message_unconfigured(client):
    r = client.post("/api/alerts/test")
    assert r.status_code == 400 and "make telegram-setup" in r.json()["detail"]
```

`backend/tests/test_watchlist_api.py`:
```python
from datetime import date

from app.keywords import get_or_create_keyword
from app.models import KeywordRelation, KeywordScore, ListingSignal, Product, Seed

D = date(2026, 10, 8)


def test_watchlist_card(client, session):
    session.add(Seed(keyword="pickleball"))
    kw = get_or_create_keyword(session, "pickleball")
    kids = [get_or_create_keyword(session, f"pickleball {w}", origin="discovered", has_parent=True)
            for w in ("queen", "dad", "mom", "coach")]
    for i, k in enumerate(kids):
        session.add(KeywordRelation(parent_id=kw.id, child_id=k.id, source="etsy", last_seen=D))
        session.add(KeywordScore(keyword_id=k.id, score=50 + i, date=D))
    session.add(KeywordScore(keyword_id=kw.id, score=61, growth=0.3, date=D))
    for i, status in enumerate(["super_breakout", "steady_grower", "steady_grower", "calibrating"]):
        p = Product(source="etsy", external_id=f"p{i}", title=f"Pickleball tee {i}", url="u",
                    image_url=f"https://img/{i}.jpg", product_type="tshirt")
        session.add(p)
        session.flush()
        session.add(ListingSignal(product_id=p.id, discovered_on=D, discovery_query="graphic tee",
                                  status=status, delta_saves=i, updated_on=D))
    session.commit()

    item = client.get("/api/watchlist").json()["items"][0]
    assert item["keyword"] == "pickleball" and item["score"] == 61 and item["growth"] == 0.3
    assert item["children_total"] == 4
    assert [c["keyword"] for c in item["children"]] == ["pickleball coach", "pickleball mom", "pickleball dad"]
    assert item["listings"] == {"super_breakout": 1, "steady_grower": 2}
    assert item["thumbnails"][0]["status"] == "super_breakout" and len(item["thumbnails"]) == 3
    assert item["alerts_7d"] == 0
```
(Thumbnails include only super_breakout + steady_grower listings.)

- [ ] **Step 2: Run** → FAIL. **Step 3:** implement (pydantic models in `schemas.py`: `AlertOut`, `AlertPage`, `UnreadCount`, `TelegramStatus`, `WatchChild`, `WatchThumb`, `WatchItem`, `WatchPage`). **Step 4:** full suite PASS.
- [ ] **Step 5: Commit** `feat(api): alerts and watchlist endpoints`.

---

### Task 7: Frontend — API client, navigation with unread badge, /watchlist page

**Files:**
- Modify: `frontend/lib/api.ts` (types + methods), `frontend/components/ui/AppShell.tsx` (nav items + badge)
- Create: `frontend/app/watchlist/page.tsx`, `frontend/components/WatchCard.tsx`

**Interfaces — Produces (lib/api.ts):**
```ts
export type AlertKind = "niche" | "listing" | "hot_product" | "amazon";
export type AlertItem = { id: number; kind: AlertKind; level: number; title: string; reason: string;
  image_url: string | null; link: string; external_url: string | null; watch_keyword: string | null;
  scan_date: string; created_at: string; read: boolean };
export type AlertPage = { unread: number; items: AlertItem[] };
export type TelegramStatus = { configured: boolean; app_url: string | null };
export type WatchItem = { seed_id: number; keyword: string; keyword_id: number; score: number | null;
  growth: number | null; children_total: number; children: { keyword_id: number; keyword: string; score: number | null }[];
  listings: { super_breakout: number; steady_grower: number };
  thumbnails: { product_id: number; image_url: string | null; title: string; url: string; status: SignalStatus }[];
  alerts_7d: number };
export type WatchPage = { date: string | null; items: WatchItem[] };
// api additions:
listAlerts: (limit = 100) => request<AlertPage>(`/api/alerts${toQuery({ limit })}`),
unreadAlerts: () => request<{ unread: number }>("/api/alerts/unread-count"),
markAlertsRead: () => request<{ unread: number }>("/api/alerts/read", { method: "POST" }),
telegramStatus: () => request<TelegramStatus>("/api/alerts/telegram"),
testTelegram: () => request<{ ok: boolean }>("/api/alerts/test", { method: "POST" }),
getWatchlist: () => request<WatchPage>("/api/watchlist"),
// SignalQuery gains: keyword?: string
```

Nav (`NAV_ITEMS`) order: Trend Radar `/`, Watchlist `/watchlist`, Listing Signals `/signals`, Amazon `/amazon`, Bán chạy `/products`, Tin mới `/alerts`, Lịch mùa vụ `/calendar`, Cài đặt `/settings`. AppShell fetches `api.unreadAlerts()` on mount and whenever `pathname` changes (ignore errors) and also listens for a `window` event `"alerts:read"` to reset to 0. When unread > 0, the "Tin mới" link shows a right-aligned pill: `ml-auto rounded-full bg-cyan px-1.5 font-mono text-[11px] font-medium leading-5 text-ink` with the count (cap display at "99+"), plus `<span className="sr-only"> chưa đọc</span>`.

`/watchlist` page:
- `PageHeader` eyebrow "Watchlist" (+ mono date), title "Ngách đang theo dõi", description "Mỗi keyword: ngách con tìm được và mẫu Etsy đang bứt phá. Thêm keyword để app quét thêm ngách.", actions = add form (input `aria-label="Keyword mới"`, placeholder "vd: volleyball mom", Button primary "Theo dõi"; on submit `api.addSeed`, 409 → Notice "Keyword đã có trong Watchlist", then reload).
- Grid `grid gap-4 md:grid-cols-2` of `WatchCard`. Empty → `EmptyState` title "Chưa theo dõi keyword nào", body "Thêm một ngách, ví dụ football mom hoặc pickleball. Dữ liệu có sau lần quét kế tiếp (8:00 hoặc 20:00)."
- `WatchCard` (Card): header row — keyword (`font-display font-wide text-lg font-extrabold`), right: `HalftoneMeter value={score/100}` + mono score + `Delta` for growth (ratio). Then `Section`-like rows with eyebrow labels:
  - "Ngách con ({children_total})": chips (TAG_CHIP from SignalCard, cyan dot) linking `/trends/{id}` with mono score; if 0: "Chưa có — chờ lần quét kế tiếp".
  - "Etsy bứt phá": `StatusBadge kind="signal" status="super_breakout"` + count, same for steady_grower; then up to 4 thumbnails 64px square using `ImageZoom` (href = url).
  - Footer: `ButtonLink` secondary "Xem chi tiết" → `/trends/{keyword_id}`; `ButtonLink` secondary "Xem listing" → `/signals?keyword=${encodeURIComponent(keyword)}&status=all`; ghost "Bỏ theo dõi" → `confirm("Bỏ theo dõi “…”?")` then `api.deleteSeed(seed_id)` and reload. If `alerts_7d > 0` show "🔔 {n} tin trong 7 ngày" linking `/alerts`.

- [ ] **Step 1:** implement types/methods; **Step 2:** AppShell nav + badge; **Step 3:** page + card.
- [ ] **Step 4: Verify** `npm run lint && npx tsc --noEmit && npm run build` all clean; with backend running, open `http://localhost:3737/watchlist` at 1440 and 390 px — no horizontal page scroll, cards render (zero data states OK).
- [ ] **Step 5: Commit** `feat(ui): Watchlist page and Tin mới nav badge`.

---

### Task 8: Frontend — /alerts page, Signals keyword filter, deep links, Settings links

**Files:**
- Create: `frontend/app/alerts/page.tsx`
- Modify: `frontend/app/signals/page.tsx`, `frontend/app/amazon/page.tsx`, `frontend/app/products/page.tsx`, `frontend/app/settings/page.tsx`

Requirements:
- **/alerts** ("Tin mới"): PageHeader eyebrow "Tin mới", title "Tin mới", description "Phát hiện sau mỗi lần quét (8:00 và 20:00): ngách bứt phá, mẫu Etsy tăng mạnh, sản phẩm hot, Amazon mới vào top."
  - Load `api.listAlerts()`; remember which ids were unread in local state; after the first successful load call `api.markAlertsRead()` then `window.dispatchEvent(new Event("alerts:read"))`.
  - Group by `scan_date` (Section title = date in mono, e.g. "08/10/2026"). Row (Card, `padded={false}`, divide-y): left icon block (🚀/🔥/⭐/🛒 with sr-only kind label), image 56px via `ImageZoom` (href = external_url ?? undefined) or a 56px paper square with `RegistrationMark` for niche; middle: kind label eyebrow + watch keyword chip, title (Link to `link`, `line-clamp-2`), reason in mono `text-xs text-ink-2`; right: external link "Etsy ↗"/"Amazon ↗" when present. Unread rows (from the remembered set) get `border-l-[3px] border-cyan`.
  - Card "Telegram" at top-right/aside (or above list on mobile): if `configured` → "Đã kết nối" with go InkDot + Button "Gửi tin thử" (calls `api.testTelegram`, shows Notice success "Đã gửi — kiểm tra Telegram" / error detail); else → Notice tone info: "Chưa kết nối Telegram. Trên máy Mac, chạy `make telegram-setup` rồi làm theo hướng dẫn."
  - Empty → EmptyState "Chưa có tin nào" / "Tin xuất hiện sau lần quét kế tiếp khi có ngách hoặc sản phẩm vượt ngưỡng (chỉnh trong backend/config/alerts.yaml)."
- **/signals**: add `Select` "Keyword" (first option "Mọi keyword", then watchlist seeds from `api.listSeeds()`), bound to `query.keyword`. Initial `query.keyword` and `query.status` read from `useSearchParams()` (`keyword`, `status` if valid). Keep URL in sync with `router.replace` on change (only `keyword` and `status`). Wrap the page content in `<Suspense>` as required by Next for `useSearchParams` in client pages (export a default wrapper component).
- **/amazon**: initial `category` from `?category=` if it is a known key.
- **/products**: initial `keyword_id` from `?keyword_id=` (number).
- **/settings**: each Watchlist keyword text becomes `Link` to `/trends/{keyword_id}`; replace the add-keyword input with a line: "Thêm/bỏ keyword ở trang " + Link "Watchlist" (`/watchlist`). Keep the delete buttons.

- [ ] **Step 1–4:** implement each page change; `npm run lint && npx tsc --noEmit && npm run build` clean.
- [ ] **Step 5: Verify in browser** (backend + `make up` running): `/alerts` empty state + Telegram card; `/signals?keyword=pickleball&status=all` preselects; `/amazon?category=men_hoodies` opens that tab; `/products?keyword_id=<id>` filters; Settings keyword links open the detail page. 390 px: no horizontal scroll.
- [ ] **Step 6: Commit** `feat(ui): Tin mới page, Signals keyword filter, deep links`.

---

### Task 9: Docs and live verification

**Files:** Modify `README.md`.

- [ ] **Step 1:** README: add section "### Watchlist & Tin mới" (what each alert means, thresholds file `backend/config/alerts.yaml`) and "### Thông báo Telegram" (create bot with @BotFather → send it any message → `make telegram-setup` → done; test button on Tin mới page; token only in `backend/.env`).
- [ ] **Step 2:** `cd backend && .venv/bin/alembic upgrade head` on the real DB; `.venv/bin/pytest -q` all green; restart servers (`make down && make up`).
- [ ] **Step 3:** Run detection once on real data without a scan: `.venv/bin/python -c "from app.config import get_settings; from app.db import make_engine, make_session_factory; from app.services.alerts import detect_alerts; import datetime; sf = make_session_factory(make_engine(get_settings().database_url)); s = sf(); a = detect_alerts(s, datetime.date.today()); s.commit(); print(len(a), sorted({x.kind for x in a}))"` — record the counts in the report; check `/alerts` and `/watchlist` render with real data.
- [ ] **Step 4: Commit** `docs: Watchlist, Tin mới and Telegram`.
