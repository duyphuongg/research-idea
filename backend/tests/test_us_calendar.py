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
        "breast_cancer_awareness", "halloween", "sale_11_11", "veterans_day",
        "thanksgiving",
        "black_friday", "cyber_monday", "sale_12_12", "christmas", "new_year",
        "black_history_month",
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
