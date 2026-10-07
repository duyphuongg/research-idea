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


def _cand(sid=1, level=1):
    status = "super_breakout" if level == 2 else "steady_grower"
    row = ListingRow(sid, "t", "u", None, status, 1, 0.1, "k", "/s")
    return listing_candidates([row])[0]


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
