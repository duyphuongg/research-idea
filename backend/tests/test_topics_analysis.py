import pytest

from app.analysis.topics import ListingGain, TopicsConfig, build_topics, load_topics_config, topic_key

GENERIC = frozenset({"shirt", "tee", "gift", "women", "for"})
CFG = TopicsConfig(min_listings=3, min_shops=2, generic_words=GENERIC, prior_weight=2)


def lg(pid, tags, gain, shop=None, prev=None):
    return ListingGain(pid, shop if shop is not None else pid, tuple(tags), gain, prev)


def test_topic_key_strips_generic_words_and_plurals():
    assert topic_key("Black Cat Shirts", GENERIC) == "black cat"
    assert topic_key("gift for women", GENERIC) is None
    assert topic_key("ab tee", GENERIC) is None  # too short once stripped


def test_load_config():
    cfg = load_topics_config()
    assert cfg.min_listings == 5 and "shirt" in cfg.generic_words and "kid" in cfg.generic_words


def background(n=10, start=100):
    return [lg(start + i, [f"misc{i}"], 1.0) for i in range(n)]


def test_hot_topic_ranks_above_average_and_counts():
    rows = background() + [lg(i, ["Black Cat Shirt", "spooky tee"], 10.0, prev=4.0) for i in range(1, 5)]
    rows += [lg(9, ["black cat tee"], 10.0), lg(8, ["black cat tee"], 10.0)]
    topics = build_topics(rows, CFG)
    top = topics[0]
    assert top.key == "black cat"
    assert top.listings == 6 and top.shops == 6 and top.rising == 6
    assert top.gain_7d == pytest.approx(60) and top.prev_gain_7d == pytest.approx(16)
    assert top.growth == pytest.approx(60 / 16 - 1)
    assert top.score > 1
    assert top.product_ids == (1, 2, 3, 4, 8, 9)  # by gain, then id
    assert top.aliases == ("spooky",)  # 4 of the same 6 listings → merged into the better topic


def test_one_viral_listing_or_one_shop_is_not_a_topic():
    viral = background() + [lg(1, ["ghost"], 100.0), lg(2, ["ghost"], 1.0), lg(3, ["ghost"], 1.0)]
    assert all(t.key != "ghost" for t in build_topics(viral, CFG))
    one_shop = background() + [lg(i, ["frog"], 5.0, shop=7) for i in range(1, 5)]
    assert all(t.key != "frog" for t in build_topics(one_shop, CFG))


def test_prior_pulls_small_topics_toward_average():
    small = [lg(i, ["tiny"], 20.0) for i in range(1, 4)]
    big = [lg(i, ["broad"], 20.0) for i in range(10, 20)]
    topics = {t.key: t for t in build_topics(background() + small + big, CFG)}
    assert topics["broad"].score > topics["tiny"].score > 1


def test_empty_or_no_growth():
    assert build_topics([], CFG) == []
    assert build_topics([lg(i, ["x y z"], 0.0) for i in range(5)], CFG) == []
