import pytest

from app.analysis.pod_filter import (
    PodFilterRules,
    adds_only_product_words,
    is_pod_relevant,
    load_rules,
    singularize,
)


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
        ("halloween costume ideas", "discovered", False, False),  # "ideas" blocked
        ("halloween costume", "discovered", False, True),
        ("ohio state buckeyes football", "discovered", False, False),  # hobbies not parentless
        ("nurse appreciation week", "discovered", False, True),
        ("nurse sweatshirt 727", "discovered", True, False),
        ("nurse class of 2026", "discovered", True, True),
        ("gift for her", "discovered", True, False),
        ("birthday gift", "discovered", True, False),
        ("funny shirt", "discovered", True, False),
        ("father's day shirt", "discovered", False, True),
        ("etsy nurse shirt", "discovered", True, False),
        ("nurse embroidery machine", "discovered", True, False),
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


def test_custom_rules_default_parentless_allows_all():
    rules = PodFilterRules(blocklist=(), allow=frozenset({"good"}))
    assert is_pod_relevant("good thing", origin="discovered", has_parent=False, rules=rules)


def test_parentless_allow_restricts_words():
    rules = PodFilterRules(blocklist=(), allow=frozenset({"a1", "b1"}), parentless_allow=frozenset({"a1"}))
    assert is_pod_relevant("a1 thing", origin="discovered", has_parent=False, rules=rules)
    assert not is_pod_relevant("b1 thing", origin="discovered", has_parent=False, rules=rules)


def test_load_rules_ignores_empty_terms(monkeypatch):
    import app.analysis.pod_filter as pf

    monkeypatch.setattr(
        pf, "load_yaml", lambda name: {"blocklist": ["bad", None, ""], "allow": {"x": ["good", None, ""]}}
    )
    rules = pf.load_rules()
    assert rules.blocklist == ("bad",)
    assert rules.allow == frozenset({"good"})


@pytest.mark.parametrize(
    "token,expected",
    [("gifts", "gift"), ("hoodies", "hoodie"), ("christmas", "christmas"), ("dress", "dress"), ("is", "is")],
)
def test_singularize(token, expected):
    assert singularize(token) == expected


@pytest.mark.parametrize(
    "text,parent,expected",
    [
        ("nurse shirts", "nurse", True),
        ("dog mom hoodie", "dog mom", True),
        ("dog moms", "dog mom", True),
        ("nurse gift", "nurse", False),
        ("halloween nurse", "nurse", False),
    ],
)
def test_adds_only_product_words(text, parent, expected):
    assert adds_only_product_words(text, parent) is expected
