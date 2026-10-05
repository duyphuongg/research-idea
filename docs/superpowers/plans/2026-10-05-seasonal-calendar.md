# POD Trend Radar — US Seasonal Calendar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Lịch mùa vụ thị trường Mỹ: ngày sự kiện (kể cả lễ di động và sale TikTok Shop), giai đoạn bán hàng tính lùi theo thời gian in/giao POD 10 ngày, lời khuyên, và gợi ý ghép ngách sự kiện × seed.

**Architecture:** Module thuần `app/analysis/us_calendar.py` (tính ngày + giai đoạn) đọc `backend/config/us_calendar.yaml`; service `app/services/calendar_ideas.py` ghép ngách từ seeds và Trend Radar; API `GET /api/calendar`; trang `/calendar` + dải "Sắp tới" trên Trend Radar.

**Tech Stack:** như hiện tại (FastAPI, SQLAlchemy, PyYAML, Next.js).

**Spec:** `docs/superpowers/specs/2026-10-05-pod-trend-radar-design.md` §14.

## Global Constraints

- `fulfillment_days: 10` (đọc từ `us_calendar.yaml`).
- Mốc tính từ ngày bắt đầu sự kiện S: design S−56, launch S−42, push S−28, ship_by S−fulfillment_days (chỉ khi `ship_by: true`; sự kiện `type: sale` có `ship_by: false`). `AFTER_DAYS = 7`.
- Giai đoạn theo thứ tự kiểm tra: `after` (today > end) → `peak` (start ≤ today ≤ end) → `cutoff` (ship_by tồn tại và today > ship_by) → `push` (today ≥ S−28) → `launch` (today ≥ S−42) → `design` (today ≥ S−56) → `upcoming`.
- Sự kiện gồm 11.11 (`sale_11_11`), 12.12 (`sale_12_12`), Black Friday, Cyber Monday.
- Không gọi mạng; UI tiếng Việt; naive dates (`date`).
- Commit trailer: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`

---

### Task 1: Calendar engine + config

**Files:**
- Create: `backend/config/us_calendar.yaml`, `backend/app/analysis/us_calendar.py`
- Test: `backend/tests/test_us_calendar.py`

**Interfaces:**
- Produces: `EventDef(key, name, type, rule: dict, duration_days=1, ship_by=True, theme_words: tuple[str, ...] = (), note="")`; `Occurrence(event, start, end)`; `Milestones(design_start, launch_by, push_from, ship_by: date | None)`; functions `nth_weekday(year, month, weekday, n)`, `last_weekday(year, month, weekday)`, `easter(year)`, `event_start(defn, year, by_key)`, `event_end(defn, start)`, `load_calendar() -> tuple[list[EventDef], int]` (events, fulfillment_days), `occurrences(defs, today, horizon_days) -> list[Occurrence]` (sorted by (start, key); includes events with `end >= today - AFTER_DAYS` and `start <= today + horizon_days`), `milestones(occ, fulfillment_days)`, `phase(occ, today, fulfillment_days) -> str`; dicts `PHASE_LABEL`, `PHASE_ADVICE`.
- Rule kinds: `fixed {month, day}`, `nth_weekday {month, weekday, n}`, `last_weekday {month, weekday}`, `easter {}`, `month {month}` (whole calendar month), `offset {of, days}`.

- [ ] **Step 1: Create `backend/config/us_calendar.yaml`**

```yaml
# Lịch mùa vụ thị trường Mỹ cho POD áo. Chỉnh tự do; ngày được tính lại mỗi năm.
# type: holiday | occasion | awareness | sale.  ship_by: cần giao trước ngày lễ?
# theme_words: từ đầu tiên dùng để ghép ngách với seed (vd "halloween nurse").
fulfillment_days: 10
events:
  - {key: new_year, name: "New Year", type: holiday, rule: {kind: fixed, month: 1, day: 1}, theme_words: [new year, "2027", cheers]}
  - {key: black_history_month, name: "Black History Month", type: awareness, rule: {kind: month, month: 2}, theme_words: [black history, melanin, juneteenth]}
  - {key: super_bowl, name: "Super Bowl", type: occasion, rule: {kind: nth_weekday, month: 2, weekday: sun, n: 2}, theme_words: [game day, football, super bowl]}
  - {key: valentines, name: "Valentine's Day", type: holiday, rule: {kind: fixed, month: 2, day: 14}, theme_words: [valentine, love, heart, galentine]}
  - {key: st_patricks, name: "St. Patrick's Day", type: holiday, rule: {kind: fixed, month: 3, day: 17}, theme_words: [st patrick, lucky, shamrock, irish]}
  - {key: autism_awareness_month, name: "Autism Awareness Month", type: awareness, rule: {kind: month, month: 4}, theme_words: [autism, puzzle, neurodiverse]}
  - {key: easter, name: "Easter", type: holiday, rule: {kind: easter}, theme_words: [easter, bunny, he is risen]}
  - {key: teacher_appreciation_week, name: "Teacher Appreciation Week", type: occasion, rule: {kind: nth_weekday, month: 5, weekday: mon, n: 1}, duration_days: 5, theme_words: [teacher appreciation, teacher, school]}
  - {key: nurses_week, name: "Nurses Week", type: occasion, rule: {kind: fixed, month: 5, day: 6}, duration_days: 7, theme_words: [nurse week, nurse appreciation, nurse]}
  - {key: mothers_day, name: "Mother's Day", type: holiday, rule: {kind: nth_weekday, month: 5, weekday: sun, n: 2}, theme_words: [mothers day, mom, mama]}
  - {key: graduation, name: "Graduation season", type: occasion, rule: {kind: fixed, month: 5, day: 15}, duration_days: 31, theme_words: [graduation, senior, class of]}
  - {key: memorial_day, name: "Memorial Day", type: holiday, rule: {kind: last_weekday, month: 5, weekday: mon}, theme_words: [memorial day, patriotic, usa]}
  - {key: pride_month, name: "Pride Month", type: awareness, rule: {kind: month, month: 6}, theme_words: [pride, rainbow, lgbtq]}
  - {key: fathers_day, name: "Father's Day", type: holiday, rule: {kind: nth_weekday, month: 6, weekday: sun, n: 3}, theme_words: [fathers day, dad, papa]}
  - {key: independence_day, name: "4th of July", type: holiday, rule: {kind: fixed, month: 7, day: 4}, theme_words: [4th of july, patriotic, america, usa]}
  - {key: back_to_school, name: "Back to School", type: occasion, rule: {kind: fixed, month: 8, day: 1}, duration_days: 31, theme_words: [back to school, first day, teacher]}
  - {key: labor_day, name: "Labor Day", type: holiday, rule: {kind: nth_weekday, month: 9, weekday: mon, n: 1}, theme_words: [labor day, usa]}
  - {key: breast_cancer_awareness, name: "Breast Cancer Awareness Month", type: awareness, rule: {kind: month, month: 10}, theme_words: [pink, breast cancer, awareness, in october we wear pink]}
  - {key: halloween, name: "Halloween", type: holiday, rule: {kind: fixed, month: 10, day: 31}, theme_words: [halloween, spooky, ghost, pumpkin, skeleton, witch, boo]}
  - {key: veterans_day, name: "Veterans Day", type: holiday, rule: {kind: fixed, month: 11, day: 11}, theme_words: [veteran, veterans day, patriotic]}
  - {key: sale_11_11, name: "TikTok Shop 11.11 Sale", type: sale, ship_by: false, rule: {kind: fixed, month: 11, day: 11}, theme_words: [gift, christmas gift]}
  - {key: thanksgiving, name: "Thanksgiving", type: holiday, rule: {kind: nth_weekday, month: 11, weekday: thu, n: 4}, theme_words: [thanksgiving, thankful, turkey, fall]}
  - {key: black_friday, name: "Black Friday", type: sale, ship_by: false, rule: {kind: offset, of: thanksgiving, days: 1}, theme_words: [christmas gift, gift]}
  - {key: cyber_monday, name: "Cyber Monday", type: sale, ship_by: false, rule: {kind: offset, of: thanksgiving, days: 4}, theme_words: [christmas gift, gift]}
  - {key: sale_12_12, name: "TikTok Shop 12.12 Sale", type: sale, ship_by: false, rule: {kind: fixed, month: 12, day: 12}, theme_words: [christmas gift, christmas]}
  - {key: christmas, name: "Christmas", type: holiday, rule: {kind: fixed, month: 12, day: 25}, theme_words: [christmas, xmas, santa, ugly sweater, family christmas]}
```

- [ ] **Step 2: Write the failing test `backend/tests/test_us_calendar.py`**

```python
from datetime import date

import pytest

from app.analysis.us_calendar import (
    EventDef,
    easter,
    event_start,
    last_weekday,
    load_calendar,
    milestones,
    nth_weekday,
    occurrences,
    phase,
)

TODAY = date(2026, 10, 5)


def defs_by_key():
    defs, _ = load_calendar()
    return defs, {d.key: d for d in defs}


def test_date_helpers():
    assert nth_weekday(2026, 11, 3, 4) == date(2026, 11, 26)  # 4th Thursday
    assert nth_weekday(2026, 5, 6, 2) == date(2026, 5, 10)  # 2nd Sunday
    assert last_weekday(2026, 5, 0) == date(2026, 5, 25)  # last Monday
    assert easter(2026) == date(2026, 4, 5)
    assert easter(2027) == date(2027, 3, 28)


@pytest.mark.parametrize(
    "key,expected",
    [
        ("thanksgiving", date(2026, 11, 26)),
        ("black_friday", date(2026, 11, 27)),
        ("cyber_monday", date(2026, 11, 30)),
        ("mothers_day", date(2026, 5, 10)),
        ("fathers_day", date(2026, 6, 21)),
        ("memorial_day", date(2026, 5, 25)),
        ("labor_day", date(2026, 9, 7)),
        ("super_bowl", date(2026, 2, 8)),
        ("teacher_appreciation_week", date(2026, 5, 4)),
        ("easter", date(2026, 4, 5)),
        ("sale_11_11", date(2026, 11, 11)),
        ("sale_12_12", date(2026, 12, 12)),
        ("breast_cancer_awareness", date(2026, 10, 1)),
    ],
)
def test_event_start_2026(key, expected):
    _, by_key = defs_by_key()
    assert event_start(by_key[key], 2026, by_key) == expected


def test_load_calendar_reads_fulfillment_days_and_sale_flags():
    defs, fulfillment = load_calendar()
    by_key = {d.key: d for d in defs}
    assert fulfillment == 10
    assert by_key["black_friday"].type == "sale" and by_key["black_friday"].ship_by is False
    assert by_key["halloween"].ship_by is True
    assert by_key["halloween"].theme_words[0] == "halloween"


def test_occurrences_next_120_days():
    defs, _ = load_calendar()
    keys = [o.event.key for o in occurrences(defs, TODAY, 120)]
    assert keys == [
        "breast_cancer_awareness", "halloween", "sale_11_11", "veterans_day", "thanksgiving",
        "black_friday", "cyber_monday", "sale_12_12", "christmas", "new_year", "black_history_month",
    ]
    month = occurrences(defs, TODAY, 120)[0]
    assert (month.start, month.end) == (date(2026, 10, 1), date(2026, 10, 31))


def test_recently_ended_event_is_kept_for_seven_days():
    defs, _ = load_calendar()
    keys = [o.event.key for o in occurrences(defs, date(2026, 11, 3), 10)]
    assert "halloween" in keys  # ended Oct 31, within AFTER_DAYS
    assert "halloween" not in [o.event.key for o in occurrences(defs, date(2026, 11, 9), 10)]


def phase_of(key, today=TODAY):
    defs, _ = load_calendar()
    occ = next(o for o in occurrences(defs, today, 400) if o.event.key == key)
    return phase(occ, today, 10), milestones(occ, 10)


def test_phases_on_2026_10_05():
    p, m = phase_of("halloween")
    assert p == "push"
    assert (m.design_start, m.launch_by, m.push_from, m.ship_by) == (
        date(2026, 9, 5), date(2026, 9, 19), date(2026, 10, 3), date(2026, 10, 21)
    )
    assert phase_of("breast_cancer_awareness")[0] == "peak"
    assert phase_of("thanksgiving")[0] == "design"
    assert phase_of("christmas")[0] == "upcoming"
    assert phase_of("sale_11_11")[0] == "launch"
    bf_phase, bf = phase_of("black_friday")
    assert bf_phase == "design" and bf.ship_by is None


def test_cutoff_and_after():
    assert phase_of("halloween", date(2026, 10, 25))[0] == "cutoff"
    assert phase_of("halloween", date(2026, 10, 31))[0] == "peak"
    assert phase_of("halloween", date(2026, 11, 2))[0] == "after"


def test_unknown_rule_kind_raises():
    bad = EventDef(key="x", name="X", type="holiday", rule={"kind": "lunar"})
    with pytest.raises(ValueError):
        event_start(bad, 2026, {"x": bad})
```

- [ ] **Step 3: Run to verify failure** — `cd backend && .venv/bin/pytest tests/test_us_calendar.py -v` → ModuleNotFoundError.

- [ ] **Step 4: Create `backend/app/analysis/us_calendar.py`**

```python
"""US seasonal calendar: event dates and selling phases for POD apparel."""

import calendar as _calendar
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from app.config_files import load_yaml

WEEKDAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
DESIGN_DAYS = 56
LAUNCH_DAYS = 42
PUSH_DAYS = 28
AFTER_DAYS = 7
DEFAULT_FULFILLMENT_DAYS = 10

PHASE_LABEL = {
    "upcoming": "Sắp tới",
    "design": "🎨 Thiết kế",
    "launch": "🚀 Lên sản phẩm",
    "push": "📈 Đẩy mạnh",
    "cutoff": "⏰ Quá hạn giao hàng",
    "peak": "🔥 Cao điểm",
    "after": "Hết mùa",
}

PHASE_ADVICE = {
    "upcoming": "Chưa cần làm gì — ghi chú ý tưởng, theo dõi ngách liên quan trên Trend Radar.",
    "design": "Nghiên cứu ngách và làm thiết kế; ưu tiên ghép sự kiện với ngách bạn đang bán.",
    "launch": "Đăng sản phẩm lên TikTok Shop, quay video mẫu, gửi sample cho KOC/affiliate.",
    "push": "Tăng ngân sách quảng cáo, livestream, đẩy affiliate; theo dõi mẫu nào bán tốt để nhân bản.",
    "cutoff": "Đơn mới có thể không kịp giao trước ngày lễ — ghi rõ thời gian giao, chuyển sang sự kiện kế tiếp.",
    "peak": "Cao điểm: không sửa listing đang chạy, giữ ngân sách quảng cáo, trả lời khách nhanh.",
    "after": "Hết mùa: dừng quảng cáo theo mùa, xả hàng, ghi lại mẫu thắng cho năm sau.",
}


@dataclass(frozen=True)
class EventDef:
    key: str
    name: str
    type: str  # holiday | occasion | awareness | sale
    rule: dict[str, Any]
    duration_days: int = 1
    ship_by: bool = True
    theme_words: tuple[str, ...] = ()
    note: str = ""


@dataclass(frozen=True)
class Occurrence:
    event: EventDef
    start: date
    end: date


@dataclass(frozen=True)
class Milestones:
    design_start: date
    launch_by: date
    push_from: date
    ship_by: date | None


def nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    first = date(year, month, 1)
    return first + timedelta(days=(weekday - first.weekday()) % 7 + 7 * (n - 1))


def last_weekday(year: int, month: int, weekday: int) -> date:
    last = date(year, month, _calendar.monthrange(year, month)[1])
    return last - timedelta(days=(last.weekday() - weekday) % 7)


def easter(year: int) -> date:
    """Anonymous Gregorian algorithm."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7  # noqa: E741
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    return date(year, month, day + 1)


def event_start(defn: EventDef, year: int, by_key: dict[str, EventDef]) -> date:
    rule = defn.rule
    kind = rule.get("kind")
    if kind == "fixed":
        return date(year, rule["month"], rule["day"])
    if kind == "nth_weekday":
        return nth_weekday(year, rule["month"], WEEKDAYS[rule["weekday"]], rule["n"])
    if kind == "last_weekday":
        return last_weekday(year, rule["month"], WEEKDAYS[rule["weekday"]])
    if kind == "easter":
        return easter(year)
    if kind == "month":
        return date(year, rule["month"], 1)
    if kind == "offset":
        return event_start(by_key[rule["of"]], year, by_key) + timedelta(days=rule["days"])
    raise ValueError(f"Unknown calendar rule kind for {defn.key}: {kind!r}")


def event_end(defn: EventDef, start: date) -> date:
    if defn.rule.get("kind") == "month":
        return date(start.year, start.month, _calendar.monthrange(start.year, start.month)[1])
    return start + timedelta(days=max(1, defn.duration_days) - 1)


def load_calendar() -> tuple[list[EventDef], int]:
    data = load_yaml("us_calendar.yaml")
    events = [
        EventDef(
            key=str(e["key"]),
            name=str(e["name"]),
            type=str(e.get("type", "holiday")),
            rule=dict(e["rule"]),
            duration_days=int(e.get("duration_days", 1)),
            ship_by=bool(e.get("ship_by", True)),
            theme_words=tuple(str(w).lower() for w in e.get("theme_words") or ()),
            note=str(e.get("note", "")),
        )
        for e in data.get("events") or []
    ]
    return events, int(data.get("fulfillment_days", DEFAULT_FULFILLMENT_DAYS))


def occurrences(defs: list[EventDef], today: date, horizon_days: int) -> list[Occurrence]:
    by_key = {d.key: d for d in defs}
    out = []
    for year in (today.year - 1, today.year, today.year + 1):
        for defn in defs:
            start = event_start(defn, year, by_key)
            end = event_end(defn, start)
            if end >= today - timedelta(days=AFTER_DAYS) and start <= today + timedelta(days=horizon_days):
                out.append(Occurrence(event=defn, start=start, end=end))
    return sorted(out, key=lambda o: (o.start, o.event.key))


def milestones(occ: Occurrence, fulfillment_days: int) -> Milestones:
    start = occ.start
    return Milestones(
        design_start=start - timedelta(days=DESIGN_DAYS),
        launch_by=start - timedelta(days=LAUNCH_DAYS),
        push_from=start - timedelta(days=PUSH_DAYS),
        ship_by=start - timedelta(days=fulfillment_days) if occ.event.ship_by else None,
    )


def phase(occ: Occurrence, today: date, fulfillment_days: int) -> str:
    m = milestones(occ, fulfillment_days)
    if today > occ.end:
        return "after"
    if occ.start <= today <= occ.end:
        return "peak"
    if m.ship_by is not None and today > m.ship_by:
        return "cutoff"
    if today >= m.push_from:
        return "push"
    if today >= m.launch_by:
        return "launch"
    if today >= m.design_start:
        return "design"
    return "upcoming"
```

Note: in `test_occurrences_next_120_days`, `veterans_day` and `sale_11_11` share Nov 11 → sorted by key (`sale_11_11` first). Wrap lines > 100 chars.

- [ ] **Step 5: Run tests** → all pass; full suite passes.

- [ ] **Step 6: Commit**

```bash
git add backend/config/us_calendar.yaml backend/app/analysis/us_calendar.py backend/tests/test_us_calendar.py
git commit -m "feat(calendar): add US seasonal calendar engine and config" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Niche ideas + Calendar API

**Files:**
- Create: `backend/app/services/calendar_ideas.py`, `backend/app/api/calendar.py`
- Modify: `backend/app/api/schemas.py` (append), `backend/app/main.py` (router)
- Test: `backend/tests/test_api_calendar.py`

**Interfaces:**
- Consumes: Task 1 functions; `Seed`, `Keyword`, `KeywordScore`; `canonical_keyword`, `normalize_keyword`; `singularize`, tokenization from `pod_filter` (`_TOKEN` is private — tokenize with `re.findall(r"[a-z0-9]+", text.lower())`).
- Produces:
  - `seed_ideas(session, occ, latest_scores: dict[int, float]) -> list[CalendarIdea]` — for each active Seed (order by id): text = `normalize_keyword(f"{occ.event.theme_words[0]} {seed.keyword}")` (skip if the event has no theme words); look up a Keyword by text, else by `canonical_keyword(text)`; idea has `keyword`, `keyword_id | None`, `score | None` (latest score), `is_seed` (Seed with that text exists).
  - `radar_matches(session, occ, latest_scores, limit=8) -> list[CalendarMatch]` — POD-relevant keywords (`is_pod_relevant`) present in `latest_scores` whose singularized token set intersects the singularized tokens of any theme word (multi-word theme words match only if all their tokens are present); sorted by score desc, then keyword; `keyword_id, keyword, score`.
  - `latest_scores(session) -> dict[int, float]` — scores of the latest `KeywordScore.date` (empty if none).
  - `GET /api/calendar?days=120&today=YYYY-MM-DD` (`days` 1–400, default 120; `today` optional, defaults to UTC today) → `CalendarPage {today, fulfillment_days, events: [CalendarEventOut]}`; `CalendarEventOut {key, name, type, start, end, days_until (start − today, may be ≤ 0), phase, phase_label, advice, note, design_start, launch_by, push_from, ship_by | None, theme_words, seed_ideas, radar_matches}`.

- [ ] **Step 1: Write the failing test `backend/tests/test_api_calendar.py`**

```python
from datetime import date

from app.keywords import get_or_create_keyword
from app.models import KeywordScore, Seed

TODAY = "2026-10-05"


def score(session, kw, value, day=date(2026, 10, 5)):
    session.add(KeywordScore(keyword_id=kw.id, date=day, score=value, sources_rising=0, sources=["etsy"]))


def test_calendar_lists_upcoming_events_with_phases(client):
    body = client.get(f"/api/calendar?today={TODAY}").json()
    assert body["today"] == TODAY and body["fulfillment_days"] == 10
    keys = [e["key"] for e in body["events"]]
    assert keys[:3] == ["breast_cancer_awareness", "halloween", "sale_11_11"]
    halloween = next(e for e in body["events"] if e["key"] == "halloween")
    assert (halloween["days_until"], halloween["phase"], halloween["ship_by"]) == (26, "push", "2026-10-21")
    assert halloween["phase_label"] == "📈 Đẩy mạnh"
    assert halloween["advice"]
    bf = next(e for e in body["events"] if e["key"] == "black_friday")
    assert (bf["type"], bf["ship_by"], bf["phase"]) == ("sale", None, "design")


def test_days_param_limits_horizon(client):
    keys = [e["key"] for e in client.get(f"/api/calendar?today={TODAY}&days=30").json()["events"]]
    assert keys == ["breast_cancer_awareness", "halloween"]
    assert client.get("/api/calendar?days=0").status_code == 422


def test_seed_ideas_and_radar_matches(client, session):
    session.add_all([Seed(keyword="nurse"), Seed(keyword="dog mom")])
    nurse_halloween = get_or_create_keyword(session, "halloween nurse", origin="discovered", has_parent=True)
    spooky = get_or_create_keyword(session, "spooky dog mom", origin="discovered", has_parent=True)
    other = get_or_create_keyword(session, "nurse gift", origin="discovered", has_parent=True)
    score(session, nurse_halloween, 50.9)
    score(session, spooky, 61.0)
    score(session, other, 70.0)
    session.commit()

    halloween = next(
        e for e in client.get(f"/api/calendar?today={TODAY}").json()["events"] if e["key"] == "halloween"
    )
    ideas = {i["keyword"]: i for i in halloween["seed_ideas"]}
    assert set(ideas) == {"halloween nurse", "halloween dog mom"}
    assert ideas["halloween nurse"]["score"] == 50.9 and ideas["halloween nurse"]["keyword_id"] == nurse_halloween.id
    assert ideas["halloween dog mom"]["keyword_id"] is None and ideas["halloween dog mom"]["is_seed"] is False
    assert [m["keyword"] for m in halloween["radar_matches"]] == ["spooky dog mom", "halloween nurse"]
```

- [ ] **Step 2: Run to verify failure** — 404.

- [ ] **Step 3: Create `backend/app/services/calendar_ideas.py`**

```python
import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analysis.pod_filter import singularize
from app.analysis.us_calendar import Occurrence
from app.api.schemas import CalendarIdea, CalendarMatch
from app.keywords import canonical_keyword, normalize_keyword
from app.models import Keyword, KeywordScore, Seed


def _tokens(text: str) -> set[str]:
    return {singularize(t) for t in re.findall(r"[a-z0-9]+", text.lower())}


def latest_scores(session: Session) -> dict[int, float]:
    latest = session.scalar(select(func.max(KeywordScore.date)))
    if latest is None:
        return {}
    rows = session.execute(
        select(KeywordScore.keyword_id, KeywordScore.score).where(KeywordScore.date == latest)
    )
    return {keyword_id: score for keyword_id, score in rows}


def seed_ideas(session: Session, occ: Occurrence, scores: dict[int, float]) -> list[CalendarIdea]:
    if not occ.event.theme_words:
        return []
    lead = occ.event.theme_words[0]
    seed_texts = set(session.scalars(select(Seed.keyword)))
    ideas = []
    for seed in session.scalars(select(Seed).where(Seed.active.is_(True)).order_by(Seed.id)):
        text = normalize_keyword(f"{lead} {seed.keyword}")
        keyword = session.scalar(select(Keyword).where(Keyword.text == text)) or session.scalar(
            select(Keyword).where(Keyword.text == canonical_keyword(text))
        )
        ideas.append(
            CalendarIdea(
                keyword=text,
                keyword_id=keyword.id if keyword else None,
                score=scores.get(keyword.id) if keyword else None,
                is_seed=text in seed_texts,
            )
        )
    return ideas


def radar_matches(
    session: Session, occ: Occurrence, scores: dict[int, float], limit: int = 8
) -> list[CalendarMatch]:
    themes = [_tokens(w) for w in occ.event.theme_words if w]
    if not themes or not scores:
        return []
    keywords = session.scalars(
        select(Keyword).where(Keyword.id.in_(scores.keys()), Keyword.is_pod_relevant.is_(True))
    )
    matches = [
        CalendarMatch(keyword_id=k.id, keyword=k.text, score=scores[k.id])
        for k in keywords
        if any(theme <= _tokens(k.text) for theme in themes)
    ]
    matches.sort(key=lambda m: (-m.score, m.keyword))
    return matches[:limit]
```

- [ ] **Step 4: Append to `backend/app/api/schemas.py`**

```python
class CalendarIdea(BaseModel):
    keyword: str
    keyword_id: int | None
    score: float | None
    is_seed: bool


class CalendarMatch(BaseModel):
    keyword_id: int
    keyword: str
    score: float


class CalendarEventOut(BaseModel):
    key: str
    name: str
    type: str
    start: date
    end: date
    days_until: int
    phase: str
    phase_label: str
    advice: str
    note: str
    design_start: date
    launch_by: date
    push_from: date
    ship_by: date | None
    theme_words: list[str]
    seed_ideas: list[CalendarIdea]
    radar_matches: list[CalendarMatch]


class CalendarPage(BaseModel):
    today: date
    fulfillment_days: int
    events: list[CalendarEventOut]
```

(The `date` type is already imported in schemas.py from Phase 2.)

- [ ] **Step 5: Create `backend/app/api/calendar.py`**

```python
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.analysis.us_calendar import (
    PHASE_ADVICE,
    PHASE_LABEL,
    load_calendar,
    milestones,
    occurrences,
    phase,
)
from app.api.deps import get_session
from app.api.schemas import CalendarEventOut, CalendarPage
from app.services.calendar_ideas import latest_scores, radar_matches, seed_ideas

router = APIRouter(prefix="/api")


@router.get("/calendar", response_model=CalendarPage)
def get_calendar(
    days: int = Query(120, ge=1, le=400),
    today: date | None = None,
    session: Session = Depends(get_session),
) -> CalendarPage:
    today = today or datetime.now(timezone.utc).date()
    defs, fulfillment_days = load_calendar()
    scores = latest_scores(session)
    events = []
    for occ in occurrences(defs, today, days):
        m = milestones(occ, fulfillment_days)
        current = phase(occ, today, fulfillment_days)
        events.append(
            CalendarEventOut(
                key=occ.event.key,
                name=occ.event.name,
                type=occ.event.type,
                start=occ.start,
                end=occ.end,
                days_until=(occ.start - today).days,
                phase=current,
                phase_label=PHASE_LABEL[current],
                advice=PHASE_ADVICE[current],
                note=occ.event.note,
                design_start=m.design_start,
                launch_by=m.launch_by,
                push_from=m.push_from,
                ship_by=m.ship_by,
                theme_words=list(occ.event.theme_words),
                seed_ideas=seed_ideas(session, occ, scores),
                radar_matches=radar_matches(session, occ, scores),
            )
        )
    return CalendarPage(today=today, fulfillment_days=fulfillment_days, events=events)
```

Note: the parameter `today` shadows nothing important; the response field is also named `today` — fine.

- [ ] **Step 6: Register router in `backend/app/main.py`** — add `calendar` to the `from app.api import ...` line and to the router loop tuple. (If the module name `calendar` collides with the stdlib inside main.py imports, import it as `from app.api import calendar as calendar_api` and use `calendar_api`.)

- [ ] **Step 7: Run tests** — `cd backend && .venv/bin/pytest -q` → all pass.

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/calendar_ideas.py backend/app/api backend/app/main.py backend/tests/test_api_calendar.py
git commit -m "feat(api): add seasonal calendar endpoint with niche ideas" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Calendar page + upcoming strip

**Files:**
- Modify: `frontend/lib/api.ts`, `frontend/app/layout.tsx`, `frontend/app/page.tsx`
- Create: `frontend/app/calendar/page.tsx`, `frontend/components/UpcomingEvents.tsx`

**Interfaces:**
- Produces: types `CalendarIdea, CalendarMatch, CalendarEvent, CalendarPage`; `api.getCalendar(days?: number)`; route `/calendar`; `<UpcomingEvents />` (shows the next 3 events with `phase !== "after"`, linking to `/calendar`).

Lint note: set state only in promise callbacks (keyed-result pattern).

- [ ] **Step 1: Edit `frontend/lib/api.ts`** — add before `async function request`:

```ts
export type CalendarIdea = { keyword: string; keyword_id: number | null; score: number | null; is_seed: boolean };
export type CalendarMatch = { keyword_id: number; keyword: string; score: number };
export type CalendarPhase = "upcoming" | "design" | "launch" | "push" | "cutoff" | "peak" | "after";
export type CalendarEvent = {
  key: string;
  name: string;
  type: "holiday" | "occasion" | "awareness" | "sale";
  start: string;
  end: string;
  days_until: number;
  phase: CalendarPhase;
  phase_label: string;
  advice: string;
  note: string;
  design_start: string;
  launch_by: string;
  push_from: string;
  ship_by: string | null;
  theme_words: string[];
  seed_ideas: CalendarIdea[];
  radar_matches: CalendarMatch[];
};
export type CalendarPage = { today: string; fulfillment_days: number; events: CalendarEvent[] };
```

and to the `api` object:

```ts
  getCalendar: (days = 120) => request<CalendarPage>(`/api/calendar${toQuery({ days })}`),
```

- [ ] **Step 2: Create `frontend/components/UpcomingEvents.tsx`**

```tsx
"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, type CalendarEvent } from "@/lib/api";

export default function UpcomingEvents() {
  const [events, setEvents] = useState<CalendarEvent[]>([]);

  useEffect(() => {
    api
      .getCalendar(120)
      .then((page) => setEvents(page.events.filter((e) => e.phase !== "after").slice(0, 3)))
      .catch(() => setEvents([]));
  }, []);

  if (events.length === 0) return null;
  return (
    <Link
      href="/calendar"
      className="mb-4 flex flex-wrap items-center gap-3 rounded-md border border-orange-200 bg-orange-50 p-3 text-sm text-orange-900 hover:bg-orange-100"
    >
      <span className="font-medium">Sắp tới:</span>
      {events.map((e) => (
        <span key={`${e.key}-${e.start}`}>
          {e.name} ({e.days_until > 0 ? `${e.days_until} ngày` : "đang diễn ra"}) · {e.phase_label}
        </span>
      ))}
      <span className="ml-auto text-xs underline">Xem lịch mùa vụ →</span>
    </Link>
  );
}
```

- [ ] **Step 3: Create `frontend/app/calendar/page.tsx`**

```tsx
"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ApiError, api, type CalendarEvent, type CalendarPage } from "@/lib/api";

type Result = { key: string; data?: CalendarPage; error?: string };

const PHASE_STYLE: Record<CalendarEvent["phase"], string> = {
  upcoming: "bg-zinc-100 text-zinc-700",
  design: "bg-purple-100 text-purple-800",
  launch: "bg-blue-100 text-blue-800",
  push: "bg-green-100 text-green-800",
  cutoff: "bg-amber-100 text-amber-800",
  peak: "bg-red-100 text-red-800",
  after: "bg-zinc-100 text-zinc-500",
};

const TYPE_LABEL: Record<CalendarEvent["type"], string> = {
  holiday: "Lễ",
  occasion: "Dịp",
  awareness: "Tháng nhận thức",
  sale: "Sale TikTok Shop",
};

function shortDate(iso: string): string {
  const [y, m, d] = iso.split("-");
  return `${d}/${m}/${y}`;
}

export default function CalendarPageView() {
  const [days, setDays] = useState(120);
  const [tick, setTick] = useState(0);
  const [result, setResult] = useState<Result | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const key = `${days}#${tick}`;
  const loading = result?.key !== key;

  useEffect(() => {
    let cancelled = false;
    api
      .getCalendar(days)
      .then((data) => !cancelled && setResult({ key, data }))
      .catch((err) => !cancelled && setResult({ key, error: String(err) }));
    return () => {
      cancelled = true;
    };
  }, [days, key]);

  async function follow(keyword: string) {
    try {
      await api.addSeed(keyword);
      setMessage(`Đã thêm “${keyword}” vào watchlist — lần quét tới sẽ lấy dữ liệu cho ngách này.`);
      setTick((t) => t + 1);
    } catch (err) {
      setMessage(err instanceof ApiError && err.status === 409 ? `“${keyword}” đã có trong watchlist.` : String(err));
    }
  }

  const page = result?.data;

  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center gap-3">
        <h1 className="mr-auto text-xl font-semibold">Lịch mùa vụ (Mỹ)</h1>
        <select
          className="rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-sm"
          value={days}
          onChange={(e) => setDays(Number(e.target.value))}
        >
          <option value={60}>60 ngày tới</option>
          <option value={120}>120 ngày tới</option>
          <option value={240}>240 ngày tới</option>
          <option value={365}>12 tháng tới</option>
        </select>
      </div>
      <p className="mb-4 text-xs text-zinc-500">
        Mốc tính lùi từ ngày sự kiện: thiết kế −8 tuần, lên sản phẩm −6 tuần, đẩy mạnh −4 tuần, hạn chót giao hàng −
        {page?.fulfillment_days ?? 10} ngày (thời gian in + giao POD, chỉnh trong backend/config/us_calendar.yaml).
      </p>
      {message && <p className="mb-3 rounded-md bg-zinc-100 p-3 text-sm">{message}</p>}
      {loading && <p className="text-sm text-zinc-500">Đang tải…</p>}
      {result?.error && !loading && <p className="text-sm text-red-600">Không tải được lịch: {result.error}</p>}

      <div className="space-y-4">
        {page?.events.map((event) => (
          <section key={`${event.key}-${event.start}`} className="rounded-lg border border-zinc-200 bg-white p-4">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-lg font-semibold">{event.name}</h2>
              <span className="text-sm text-zinc-500">
                {shortDate(event.start)}
                {event.end !== event.start && <> – {shortDate(event.end)}</>}
              </span>
              <span className="rounded bg-zinc-100 px-1.5 py-0.5 text-xs text-zinc-600">{TYPE_LABEL[event.type]}</span>
              <span className={`rounded px-1.5 py-0.5 text-xs ${PHASE_STYLE[event.phase]}`}>{event.phase_label}</span>
              <span className="ml-auto text-sm font-medium">
                {event.days_until > 0 ? `còn ${event.days_until} ngày` : event.phase === "after" ? "đã qua" : "đang diễn ra"}
              </span>
            </div>
            <p className="mt-2 text-sm">{event.advice}</p>
            {event.note && <p className="mt-1 text-xs text-zinc-500">{event.note}</p>}
            <p className="mt-2 text-xs text-zinc-500">
              Thiết kế từ {shortDate(event.design_start)} · lên sản phẩm trước {shortDate(event.launch_by)} · đẩy mạnh từ{" "}
              {shortDate(event.push_from)}
              {event.ship_by && <> · hạn chót giao hàng {shortDate(event.ship_by)}</>}
            </p>

            {event.seed_ideas.length > 0 && (
              <div className="mt-3">
                <p className="mb-1 text-xs font-medium uppercase text-zinc-500">Ghép với ngách của bạn</p>
                <div className="flex flex-wrap gap-2">
                  {event.seed_ideas.map((idea) => (
                    <span
                      key={idea.keyword}
                      className="flex items-center gap-1 rounded-full border border-zinc-300 px-3 py-1 text-sm"
                    >
                      {idea.keyword_id ? (
                        <Link href={`/trends/${idea.keyword_id}`} className="hover:underline">
                          {idea.keyword}
                        </Link>
                      ) : (
                        idea.keyword
                      )}
                      {idea.score !== null && <span className="text-xs text-zinc-400">{Math.round(idea.score)}</span>}
                      {!idea.is_seed && (
                        <button onClick={() => follow(idea.keyword)} className="text-xs text-orange-600 hover:underline">
                          + Theo dõi
                        </button>
                      )}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {event.radar_matches.length > 0 && (
              <div className="mt-3">
                <p className="mb-1 text-xs font-medium uppercase text-zinc-500">Đang có trên Trend Radar</p>
                <div className="flex flex-wrap gap-2">
                  {event.radar_matches.map((m) => (
                    <Link
                      key={m.keyword_id}
                      href={`/trends/${m.keyword_id}`}
                      className="rounded-full bg-zinc-100 px-3 py-1 text-sm hover:bg-zinc-200"
                    >
                      {m.keyword} <span className="text-xs text-zinc-500">{Math.round(m.score)}</span>
                    </Link>
                  ))}
                </div>
              </div>
            )}
          </section>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Edit `frontend/app/layout.tsx`** — add a nav link after "Trend Radar":

```tsx
            <Link href="/calendar" className="text-zinc-600 hover:text-zinc-900">
              Lịch mùa vụ
            </Link>
```

- [ ] **Step 5: Edit `frontend/app/page.tsx`** — import `UpcomingEvents from "@/components/UpcomingEvents"` and render `<UpcomingEvents />` right after `<SourceHealthBanner />`.

- [ ] **Step 6: Verify** — `cd frontend && npm run lint && npm run build` → clean; build lists `/calendar`.

- [ ] **Step 7: Commit**

```bash
git add frontend
git commit -m "feat(frontend): add seasonal calendar page and upcoming events strip" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: README + live check

**Files:** Modify `README.md`

- [ ] **Step 1: Add to README after the Trend Radar section**

```markdown
## Lịch mùa vụ (Mỹ)

Trang **Lịch mùa vụ**: các dịp bán áo POD ở Mỹ (lễ lớn, Back to School, Nurses Week, tháng nhận thức, sale TikTok Shop 11.11 / 12.12 / Black Friday / Cyber Monday) với số ngày còn lại, giai đoạn hiện tại và việc nên làm.
Mốc tính lùi: thiết kế −8 tuần, lên sản phẩm −6 tuần, đẩy mạnh −4 tuần, hạn chót giao hàng −10 ngày (in + giao POD).
Mỗi sự kiện gợi ý ghép với seed của bạn (vd "halloween nurse") và liệt kê keyword liên quan đang có trên Trend Radar.
Chỉnh sự kiện / thời gian giao hàng trong `backend/config/us_calendar.yaml`.
```

- [ ] **Step 2: Verify** — `make test`; `cd frontend && npm run lint && npm run build`; start backend on :8000 and `curl -s 'localhost:8000/api/calendar?days=120' | head -c 1500` (expect Breast Cancer Awareness, Halloween in "push", seed ideas for the user's seeds); start frontend (`npx next start -p 3000`) and check `/calendar` and `/` return 200; stop both servers.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: document seasonal calendar" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
