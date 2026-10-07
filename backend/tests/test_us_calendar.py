from datetime import date

import pytest

from app.analysis.us_calendar import (
    EventDef,
    Occurrence,
    advice_for,
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
    defs = load_calendar().events
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
        ("black_friday", date(2026, 11, 14)),
        ("mothers_day", date(2026, 5, 10)),
        ("fathers_day", date(2026, 6, 21)),
        ("memorial_day", date(2026, 5, 25)),
        ("labor_day", date(2026, 9, 7)),
        ("super_bowl", date(2026, 2, 8)),
        ("teacher_appreciation_week", date(2026, 5, 4)),
        ("mardi_gras", date(2026, 2, 17)),
        ("grandparents_day", date(2026, 9, 13)),
        ("juneteenth", date(2026, 6, 19)),
        ("easter", date(2026, 4, 5)),
        ("sale_11_11", date(2026, 11, 8)),
        ("sale_12_12", date(2026, 12, 9)),
        ("breast_cancer_awareness", date(2026, 10, 1)),
    ],
)
def test_event_start_2026(key, expected):
    _, by_key = defs_by_key()
    assert event_start(by_key[key], 2026, by_key) == expected


def test_load_calendar_reads_fulfillment_days_and_sale_flags():
    cfg = load_calendar()
    defs, fulfillment = cfg.events, cfg.fulfillment_days
    assert cfg.ship_buffer_days == 3
    by_key = {d.key: d for d in defs}
    assert fulfillment == 10
    assert by_key["black_friday"].type == "sale" and by_key["black_friday"].ship_by is False
    assert by_key["halloween"].ship_by is True
    assert by_key["halloween"].theme_words[0] == "halloween"


def test_occurrences_next_120_days():
    defs = load_calendar().events
    keys = [o.event.key for o in occurrences(defs, TODAY, 120)]
    assert keys == [
        "hispanic_heritage_month", "breast_cancer_awareness", "halloween",
        "dia_de_los_muertos", "sale_11_11", "veterans_day", "black_friday",
        "thanksgiving", "sale_12_12", "christmas", "new_year",
        "black_history_month",
    ]
    occs = occurrences(defs, TODAY, 120)
    assert (occs[1].start, occs[1].end) == (date(2026, 10, 1), date(2026, 10, 31))
    assert (occs[0].start, occs[0].end) == (date(2026, 9, 15), date(2026, 10, 15))


def test_recently_ended_event_is_kept_for_seven_days():
    defs = load_calendar().events
    keys = [o.event.key for o in occurrences(defs, date(2026, 11, 3), 10)]
    assert "halloween" in keys  # ended Oct 31, within AFTER_DAYS
    assert "halloween" not in [o.event.key for o in occurrences(defs, date(2026, 11, 9), 10)]


def phase_of(key, today=TODAY):
    defs = load_calendar().events
    occ = next(o for o in occurrences(defs, today, 400) if o.event.key == key)
    return phase(occ, today, 10, 3), milestones(occ, 10, 3)


def test_phases_on_2026_10_05():
    p, m = phase_of("halloween")
    assert p == "push"
    assert (m.design_start, m.launch_by, m.push_from, m.ship_by) == (
        date(2026, 8, 22), date(2026, 9, 11), date(2026, 10, 1), date(2026, 10, 18)
    )
    assert phase_of("breast_cancer_awareness")[0] == "peak"
    assert phase_of("thanksgiving")[0] == "design"
    assert phase_of("christmas")[0] == "design"
    assert phase_of("sale_11_11")[0] == "launch"
    bf_phase, bf = phase_of("black_friday")
    assert bf_phase == "launch" and bf.ship_by is None and bf.order_by is None


def test_cutoff_and_after():
    assert phase_of("halloween", date(2026, 10, 19))[0] == "cutoff"
    assert phase_of("halloween", date(2026, 10, 31))[0] == "peak"
    assert phase_of("halloween", date(2026, 11, 2))[0] == "after"


def test_unknown_rule_kind_raises():
    bad = EventDef(key="x", name="X", type="holiday", rule={"kind": "lunar"})
    with pytest.raises(ValueError):
        event_start(bad, 2026, {"x": bad})


def test_nth_weekday_min_day():
    assert nth_weekday(2023, 5, 0, 1, min_day=2) == date(2023, 5, 8)
    assert nth_weekday(2026, 5, 0, 1, min_day=2) == date(2026, 5, 4)
    assert nth_weekday(2028, 5, 0, 1, min_day=2) == date(2028, 5, 8)
    assert nth_weekday(2026, 5, 0, 1) == date(2026, 5, 4)


@pytest.mark.parametrize(
    "year,expected",
    [(2023, date(2023, 5, 8)), (2026, date(2026, 5, 4)), (2028, date(2028, 5, 8))],
)
def test_teacher_appreciation_week_is_first_full_week(year, expected):
    _, by_key = defs_by_key()
    assert event_start(by_key["teacher_appreciation_week"], year, by_key) == expected


def test_occurrences_cover_years_through_horizon():
    defs = load_calendar().events
    occs = occurrences(defs, TODAY, 800)  # horizon ends Dec 2028
    assert any(o.event.key == "thanksgiving" and o.start == date(2028, 11, 23) for o in occs)


def test_removed_theme_words():
    _, by_key = defs_by_key()
    assert "2027" not in by_key["new_year"].theme_words
    assert "awareness" not in by_key["breast_cancer_awareness"].theme_words
    assert "juneteenth" not in by_key["black_history_month"].theme_words


def _patch_yaml(monkeypatch, events):
    monkeypatch.setattr(
        "app.analysis.us_calendar.load_yaml", lambda name: {"events": events}
    )


@pytest.mark.parametrize(
    "event,match",
    [
        ({"name": "A", "rule": {"kind": "easter"}}, "key"),
        ({"key": "a", "rule": {"kind": "easter"}}, "a"),
        ({"key": "a", "name": "A"}, "a"),
    ],
)
def test_load_calendar_missing_field(monkeypatch, event, match):
    _patch_yaml(monkeypatch, [event])
    with pytest.raises(ValueError, match=match):
        load_calendar()


def test_load_calendar_duplicate_keys(monkeypatch):
    ev = {"key": "dup", "name": "D", "rule": {"kind": "easter"}}
    _patch_yaml(monkeypatch, [ev, dict(ev)])
    with pytest.raises(ValueError, match="dup"):
        load_calendar()


def test_event_start_unknown_offset_target_raises_value_error():
    bad = EventDef(
        key="x", name="X", type="holiday", rule={"kind": "offset", "of": "nope", "days": 1}
    )
    with pytest.raises(ValueError, match="nope"):
        event_start(bad, 2026, {"x": bad})


def test_event_start_missing_rule_field_raises_value_error():
    bad = EventDef(key="x", name="X", type="holiday", rule={"kind": "fixed", "month": 1})
    with pytest.raises(ValueError, match="x"):
        event_start(bad, 2026, {"x": bad})


T2 = date(2026, 10, 7)


def occ_of(key, today=T2):
    defs = load_calendar().events
    return next(o for o in occurrences(defs, today, 400) if o.event.key == key)


def test_ship_by_includes_buffer_and_order_by():
    m = milestones(occ_of("halloween"), 10, 3)
    assert m.ship_by == date(2026, 10, 18) and m.order_by == date(2026, 10, 18)
    assert milestones(occ_of("christmas"), 10, 3).ship_by == date(2026, 12, 12)
    # multi-day: end Oct 31 - 13 days = Oct 18; Hispanic end Oct 15 - 13 = Oct 2
    assert milestones(occ_of("breast_cancer_awareness"), 10, 3).order_by == date(2026, 10, 18)
    assert milestones(occ_of("hispanic_heritage_month"), 10, 3).order_by == date(2026, 10, 2)
    assert milestones(occ_of("sale_11_11"), 10, 3).order_by is None


def test_cutoff_label_and_advice():
    from app.analysis.us_calendar import PHASE_ADVICE, PHASE_LABEL

    assert PHASE_LABEL["cutoff"] == "⏰ Quá hạn đặt hàng"
    assert "hạn chót đặt hàng" in PHASE_ADVICE["cutoff"]
    assert "xả hàng" not in PHASE_ADVICE["after"]


def test_sales_are_campaigns():
    defs = load_calendar().events
    by_key = {d.key: d for d in defs}
    assert "cyber_monday" not in by_key
    bf = by_key["black_friday"]
    assert bf.name == "Black Friday – Cyber Monday" and bf.duration_days == 17
    assert bf.note == "Kiểm tra hạn đăng ký chiến dịch trong TikTok Shop Seller Center."
    o = occ_of("black_friday")
    assert (o.start, o.end) == (date(2026, 11, 14), date(2026, 11, 30))
    o = occ_of("sale_11_11")
    assert (o.start, o.end) == (date(2026, 11, 8), date(2026, 11, 11))
    o = occ_of("sale_12_12")
    assert (o.start, o.end) == (date(2026, 12, 9), date(2026, 12, 12))
    assert "11.11" in by_key["sale_11_11"].name and "12.12" in by_key["sale_12_12"].name


def test_per_event_lead_times():
    m = milestones(occ_of("christmas"), 10, 3)
    assert (m.design_start, m.launch_by, m.push_from) == (
        date(2026, 9, 26), date(2026, 10, 26), date(2026, 11, 15)
    )
    assert phase(occ_of("christmas"), T2, 10, 3) == "design"
    m = milestones(occ_of("halloween"), 10, 3)
    assert (m.design_start, m.launch_by, m.push_from) == (
        date(2026, 8, 22), date(2026, 9, 11), date(2026, 10, 1)
    )
    assert phase(occ_of("halloween"), T2, 10, 3) == "push"
    assert "Black Friday" in {d.key: d for d in load_calendar().events}["christmas"].note


def test_peak_advice_for_multi_day_events():
    from app.analysis.us_calendar import PHASE_ADVICE

    bca = occ_of("breast_cancer_awareness")
    assert phase(bca, T2, 10, 3) == "peak"
    adv = advice_for(bca, "peak", T2, milestones(bca, 10, 3))
    assert adv.startswith("Vẫn kịp") and "18/10" in adv
    hh = occ_of("hispanic_heritage_month")
    assert phase(hh, T2, 10, 3) == "peak"
    assert advice_for(hh, "peak", T2, milestones(hh, 10, 3)) == PHASE_ADVICE["peak"]
    s = occ_of("sale_11_11")
    assert advice_for(s, "after", T2, milestones(s, 10, 3)).startswith("Sale đã qua")
    h = occ_of("halloween")
    assert advice_for(h, "after", T2, milestones(h, 10, 3)) == PHASE_ADVICE["after"]


@pytest.mark.parametrize(
    "event,match",
    [
        ({"key": "a", "name": "A", "type": "bogus", "rule": {"kind": "easter"}}, "a"),
        ({"key": "a", "name": "A", "rule": {"kind": "fixed", "month": 2, "day": 30}}, "a"),
        ({"key": "a", "name": "A", "rule": {"kind": "offset", "of": "a", "days": 1}}, "a"),
    ],
)
def test_load_calendar_validates_type_and_rules(monkeypatch, event, match):
    _patch_yaml(monkeypatch, [event])
    with pytest.raises(ValueError, match=match):
        load_calendar()


def test_offset_cycle_names_event(monkeypatch):
    evs = [
        {"key": "p", "name": "P", "rule": {"kind": "offset", "of": "q", "days": 1}},
        {"key": "q", "name": "Q", "rule": {"kind": "offset", "of": "p", "days": 1}},
    ]
    _patch_yaml(monkeypatch, evs)
    with pytest.raises(ValueError, match="'p'|'q'"):
        load_calendar()
