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
    "upcoming": (
        "Chưa cần làm gì — ghi chú ý tưởng, theo dõi ngách liên quan trên "
        "Trend Radar."
    ),
    "design": (
        "Nghiên cứu ngách và làm thiết kế; ưu tiên ghép sự kiện với ngách "
        "bạn đang bán."
    ),
    "launch": (
        "Đăng sản phẩm lên TikTok Shop, quay video mẫu, gửi sample cho "
        "KOC/affiliate."
    ),
    "push": (
        "Tăng ngân sách quảng cáo, livestream, đẩy affiliate; theo dõi "
        "mẫu nào bán tốt để nhân bản."
    ),
    "cutoff": (
        "Đơn mới có thể không kịp giao trước ngày lễ — ghi rõ thời gian "
        "giao, chuyển sang sự kiện kế tiếp."
    ),
    "peak": (
        "Cao điểm: không sửa listing đang chạy, giữ ngân sách quảng cáo, "
        "trả lời khách nhanh."
    ),
    "after": (
        "Hết mùa: dừng quảng cáo theo mùa, xả hàng, ghi lại mẫu thắng "
        "cho năm sau."
    ),
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
        return nth_weekday(
            year, rule["month"], WEEKDAYS[rule["weekday"]], rule["n"]
        )
    if kind == "last_weekday":
        return last_weekday(year, rule["month"], WEEKDAYS[rule["weekday"]])
    if kind == "easter":
        return easter(year)
    if kind == "month":
        return date(year, rule["month"], 1)
    if kind == "offset":
        return event_start(by_key[rule["of"]], year, by_key) + timedelta(
            days=rule["days"]
        )
    raise ValueError(f"Unknown calendar rule kind for {defn.key}: {kind!r}")


def event_end(defn: EventDef, start: date) -> date:
    if defn.rule.get("kind") == "month":
        return date(
            start.year,
            start.month,
            _calendar.monthrange(start.year, start.month)[1],
        )
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


def occurrences(
    defs: list[EventDef], today: date, horizon_days: int
) -> list[Occurrence]:
    by_key = {d.key: d for d in defs}
    out = []
    for year in (today.year - 1, today.year, today.year + 1):
        for defn in defs:
            start = event_start(defn, year, by_key)
            end = event_end(defn, start)
            if (
                end >= today - timedelta(days=AFTER_DAYS)
                and start <= today + timedelta(days=horizon_days)
            ):
                out.append(Occurrence(event=defn, start=start, end=end))
    return sorted(out, key=lambda o: (o.start, o.event.key))


def milestones(occ: Occurrence, fulfillment_days: int) -> Milestones:
    start = occ.start
    return Milestones(
        design_start=start - timedelta(days=DESIGN_DAYS),
        launch_by=start - timedelta(days=LAUNCH_DAYS),
        push_from=start - timedelta(days=PUSH_DAYS),
        ship_by=(
            start - timedelta(days=fulfillment_days) if occ.event.ship_by else None
        ),
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
