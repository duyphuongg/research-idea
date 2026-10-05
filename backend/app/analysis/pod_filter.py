import re
from dataclasses import dataclass
from functools import lru_cache

from app.config_files import load_yaml

_TOKEN = re.compile(r"[a-z0-9']+")


@dataclass(frozen=True)
class PodFilterRules:
    blocklist: tuple[str, ...]
    allow: frozenset[str]


@lru_cache
def load_rules() -> PodFilterRules:
    data = load_yaml("pod_filter.yaml")
    blocklist = tuple(" ".join(str(t).lower().split()) for t in data.get("blocklist", []))
    allow = frozenset(
        str(word).lower() for group in (data.get("allow") or {}).values() for word in group
    )
    return PodFilterRules(blocklist=blocklist, allow=allow)


def is_pod_relevant(
    text: str, *, origin: str, has_parent: bool, rules: PodFilterRules | None = None
) -> bool:
    if origin == "seed":
        return True
    rules = rules or load_rules()
    normalized = " ".join(text.lower().split())
    for term in rules.blocklist:
        if re.search(rf"\b{re.escape(term)}\b", normalized):
            return False
    if has_parent:
        return True
    tokens = set(_TOKEN.findall(normalized))
    tokens |= {t[:-1] for t in tokens if t.endswith("s") and len(t) > 3}
    return bool(tokens & rules.allow)
