import pytest

from app.analysis.pod_filter import PodFilterRules, is_pod_relevant, load_rules


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
        ("halloween costume ideas", "discovered", False, True),
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
