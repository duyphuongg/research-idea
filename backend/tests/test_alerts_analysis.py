from datetime import datetime, timedelta

from app.analysis.alerts import (
    AlertsConfig, HotRow, ListingRow, NicheRow, PastAlert, ShopRow,
    dedupe, hot_candidates, listing_candidates, niche_candidates, shop_candidates, telegram_order,
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
        ("niche", 1, 70.0), ("listing", 2, 1.0), ("shop", 1, 40.0),
    ], key=lambda k: telegram_order(*k))
    # an unknown kind (e.g. a leftover "amazon" row) sorts last
    assert [k[0] for k in keys] == ["listing", "niche", "listing", "shop", "hot_product", "amazon"]
    assert keys[0][1] == 2


def _shop(sid, sales, days=7, prev=None):
    return ShopRow(sid, f"Shop{sid}", f"https://www.etsy.com/shop/S{sid}", f"https://img/s{sid}.jpg",
                   sales, days, prev)


def test_shop_needs_full_week_minimum_and_growth():
    rows = [
        _shop(1, 30),               # no previous week: minimum is enough
        _shop(2, 29),               # below minimum
        _shop(3, 60, days=6),       # less than a full week of history
        _shop(4, 45, prev=30),      # exactly 1.5x
        _shop(5, 44, prev=30),      # below 1.5x
        _shop(6, 30, prev=0),       # previous week 0 counts as 1
    ]
    out = {c.subject_id: c for c in shop_candidates(rows, CFG)}
    assert set(out) == {1, 4, 6}
    c = out[4]
    assert (c.kind, c.level, c.priority, c.title) == ("shop", 1, 45, "Shop4")
    assert c.reason == "+45 đơn/7 ngày (tuần trước +30)"
    assert out[1].reason == "+30 đơn/7 ngày"
    assert (c.image_url, c.link, c.external_url, c.watch_keyword) == (
        "https://img/s4.jpg", "/shops/4", "https://www.etsy.com/shop/S4", None)


def test_shop_thresholds_from_config():
    cfg = AlertsConfig(shop_min_sales_7d=10, shop_growth=2.0)
    out = shop_candidates([_shop(1, 10), _shop(2, 19, prev=10), _shop(3, 20, prev=10)], cfg)
    assert [c.subject_id for c in out] == [1, 3]


def test_shop_needs_a_7_to_9_day_span():
    rows = [_shop(1, 60, days=7), _shop(2, 60, days=9), _shop(3, 60, days=10), _shop(4, 60, days=45)]
    assert [c.subject_id for c in shop_candidates(rows, CFG)] == [1, 2]


def _shop_pd(sid, sales, prev, prev_days):
    return ShopRow(sid, f"Shop{sid}", None, None, sales, 7, prev, prev_days)


def test_shop_prev_over_under_3_days_is_unknown():
    # prev 20 over 2 days: unknown, growth check skipped (35 would fail 1.5x of the raw-scaled 70)
    out = shop_candidates([_shop_pd(1, 35, 20, 2)], CFG)
    assert [c.subject_id for c in out] == [1]
    assert out[0].reason == "+35 đơn/7 ngày"


def test_shop_prev_is_normalised_to_7_days():
    # prev 20 over 4 days -> 35 per 7 days
    rows = [_shop_pd(1, 52, 20, 4), _shop_pd(2, 53, 20, 4)]  # 1.5 * 35 = 52.5
    out = {c.subject_id: c for c in shop_candidates(rows, CFG)}
    assert set(out) == {2}
    assert out[2].reason == "+53 đơn/7 ngày (tuần trước +35)"


def test_nfl_candidates_threshold_cap_and_text():
    from app.analysis.alerts import NflRow, nfl_candidates

    rows = [
        NflRow("4241389", "CeeDee Lamb", "DAL", "WR", 90.4, ["17 REC, 189 YDS, 1 TD"], 507, False, "https://h/1.png", 4),
        NflRow("2", "Second", "CAR", "WR", 87, ["14 REC, 192 YDS, 2 TD"], None, True, None, 4),
        NflRow("3", "Third", "ATL", "RB", 86, ["x"], 1, False, None, 4),
        NflRow("4", "Fourth", "CHI", "RB", 85.5, ["y"], 1, False, None, 4),
        NflRow("5", "Low", "NE", "QB", 84.9, ["z"], 1, False, None, 4),
    ]
    cands = nfl_candidates(rows, AlertsConfig(nfl_min_potential=85, nfl_max_per_week=3))
    assert [c.subject_id for c in cands] == [4241389, 2, 3]
    lamb = cands[0]
    assert lamb.kind == "nfl" and lamb.title == "CeeDee Lamb (DAL · WR)"
    assert lamb.reason == "Tuần 4 · 17 REC, 189 YDS, 1 TD · tiềm năng 90 · Etsy 507 listing"
    assert lamb.link == "/nfl" and lamb.image_url == "https://h/1.png"
    assert "🔥 đang trend" in cands[1].reason and "Etsy" not in cands[1].reason
    assert nfl_candidates([NflRow("x", "Bad Id", None, None, 99, [], None, False, None, 4)], CFG) == []
