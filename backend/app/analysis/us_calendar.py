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
DEFAULT_SHIP_BUFFER_DAYS = 3
EVENT_TYPES = {"holiday", "occasion", "awareness", "sale"}

PHASE_LABEL = {
    "upcoming": "Sắp tới",
    "design": "🎨 Thiết kế",
    "launch": "🚀 Lên sản phẩm",
    "push": "📈 Đẩy mạnh",
    "cutoff": "⏰ Quá hạn đặt hàng",
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
        "Đã quá hạn chót đặt hàng — đơn mới có thể không kịp giao trước "
        "sự kiện; ghi rõ thời gian giao, chuyển sang sự kiện kế tiếp."
    ),
    "peak": (
        "Cao điểm: không sửa listing đang chạy, giữ ngân sách quảng cáo, "
        "trả lời khách nhanh."
    ),
    "after": (
        "Hết mùa: dừng quảng cáo theo mùa, ghi lại mẫu thắng cho năm sau, "
        "chuyển sang sự kiện kế tiếp."
    ),
}
SALE_AFTER_ADVICE = (
    "Sale đã qua — chuyển ngân sách sang sự kiện kế tiếp, giữ lại mẫu bán tốt."
)


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
    idea_template: str = "{lead} {seed}"
    cross_seeds: bool = True
    lead_days: tuple[int, int, int] = (DESIGN_DAYS, LAUNCH_DAYS, PUSH_DAYS)


@dataclass(frozen=True)
class CalendarConfig:
    events: list[EventDef]
    fulfillment_days: int
    ship_buffer_days: int


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
    order_by: date | None


def nth_weekday(
    year: int, month: int, weekday: int, n: int, min_day: int = 1
) -> date:
    """n-th given weekday on or after day `min_day` of the month."""
    first = date(year, month, min_day)
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
    try:
        return _event_start(defn, year, by_key)
    except KeyError as exc:
        raise ValueError(
            f"Calendar event {defn.key!r}: missing or unknown {exc.args[0]!r} in rule"
        ) from exc


def _event_start(defn: EventDef, year: int, by_key: dict[str, EventDef]) -> date:
    rule = defn.rule
    kind = rule.get("kind")
    if kind == "fixed":
        return date(year, rule["month"], rule["day"])
    if kind == "nth_weekday":
        return nth_weekday(
            year,
            rule["month"],
            WEEKDAYS[rule["weekday"]],
            rule["n"],
            rule.get("min_day", 1),
        )
    if kind == "last_weekday":
        return last_weekday(year, rule["month"], WEEKDAYS[rule["weekday"]])
    if kind == "easter":
        return easter(year)
    if kind == "month":
        return date(year, rule["month"], 1)
    if kind == "offset":
        return _event_start(by_key[rule["of"]], year, by_key) + timedelta(
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


def _parse_event(e: Any) -> EventDef:
    if not isinstance(e, dict):
        raise ValueError(f"Calendar event must be a mapping, got {e!r}")
    label = e.get("key") or e.get("name") or "<unnamed>"
    for field in ("key", "name", "rule"):
        if not e.get(field):
            raise ValueError(f"Calendar event {label!r} is missing {field!r}")
    etype = str(e.get("type", "holiday"))
    if etype not in EVENT_TYPES:
        raise ValueError(
            f"Calendar event {label!r}: type must be one of {sorted(EVENT_TYPES)}, got {etype!r}"
        )
    lead = e.get("lead_days") or {}
    lead_days = (
        int(lead.get("design", DESIGN_DAYS)),
        int(lead.get("launch", LAUNCH_DAYS)),
        int(lead.get("push", PUSH_DAYS)),
    )
    return EventDef(
        key=str(e["key"]),
        name=str(e["name"]),
        type=etype,
        rule=dict(e["rule"]),
        duration_days=int(e.get("duration_days", 1)),
        ship_by=bool(e.get("ship_by", True)),
        theme_words=tuple(str(w).lower() for w in e.get("theme_words") or ()),
        note=str(e.get("note", "")),
        idea_template=str(e.get("idea_template", "{lead} {seed}")),
        cross_seeds=bool(e.get("cross_seeds", True)),
        lead_days=lead_days,
    )


def load_calendar() -> CalendarConfig:
    data = load_yaml("us_calendar.yaml")
    events = [_parse_event(e) for e in data.get("events") or []]
    seen: set[str] = set()
    for e in events:
        if e.key in seen:
            raise ValueError(f"Duplicate calendar event key {e.key!r}")
        seen.add(e.key)
    by_key = {e.key: e for e in events}
    year = date.today().year
    for e in events:
        try:
            event_start(e, year, by_key)
        except RecursionError as exc:
            raise ValueError(
                f"Calendar event {e.key!r}: offset rule forms a cycle"
            ) from exc
        except ValueError as exc:
            if repr(e.key) in str(exc):
                raise
            raise ValueError(f"Calendar event {e.key!r}: invalid rule ({exc})") from exc
    return CalendarConfig(
        events=events,
        fulfillment_days=int(data.get("fulfillment_days", DEFAULT_FULFILLMENT_DAYS)),
        ship_buffer_days=int(data.get("ship_buffer_days", DEFAULT_SHIP_BUFFER_DAYS)),
    )


def occurrences(
    defs: list[EventDef], today: date, horizon_days: int
) -> list[Occurrence]:
    by_key = {d.key: d for d in defs}
    out = []
    last_year = (today + timedelta(days=horizon_days)).year + 1
    for year in range(today.year - 1, last_year + 1):
        for defn in defs:
            start = event_start(defn, year, by_key)
            end = event_end(defn, start)
            if (
                end >= today - timedelta(days=AFTER_DAYS)
                and start <= today + timedelta(days=horizon_days)
            ):
                out.append(Occurrence(event=defn, start=start, end=end))
    return sorted(out, key=lambda o: (o.start, o.event.key))


def milestones(
    occ: Occurrence,
    fulfillment_days: int,
    ship_buffer_days: int = DEFAULT_SHIP_BUFFER_DAYS,
) -> Milestones:
    start = occ.start
    design, launch, push = occ.event.lead_days
    lead = fulfillment_days + ship_buffer_days
    ship_by = order_by = None
    if occ.event.ship_by:
        ship_by = start - timedelta(days=lead)
        order_by = max(ship_by, occ.end - timedelta(days=lead))
    return Milestones(
        design_start=start - timedelta(days=design),
        launch_by=start - timedelta(days=launch),
        push_from=start - timedelta(days=push),
        ship_by=ship_by,
        order_by=order_by,
    )


def phase(
    occ: Occurrence,
    today: date,
    fulfillment_days: int,
    ship_buffer_days: int = DEFAULT_SHIP_BUFFER_DAYS,
) -> str:
    m = milestones(occ, fulfillment_days, ship_buffer_days)
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


def advice_for(occ: Occurrence, current: str, today: date, m: Milestones) -> str:
    if current == "peak" and m.order_by is not None and today <= m.order_by:
        return (
            "Vẫn kịp: lên mẫu mới và đẩy quảng cáo — đặt trước "
            f"{m.order_by:%d/%m} vẫn giao kịp trong sự kiện."
        )
    if current == "after" and occ.event.type == "sale":
        return SALE_AFTER_ADVICE
    return PHASE_ADVICE[current]
