import re
from dataclasses import dataclass

from app.config_files import load_yaml

_TOKEN = re.compile(r"[a-z0-9]+")
_POSSESSIVE = re.compile(r"[’']s\b")
_YEAR = re.compile(r"(19|20)\d\d")

APPAREL_WORDS = frozenset(
    {
        "shirt", "tee", "tshirt", "t", "hoodie", "sweatshirt", "crewneck", "sweater",
        "apparel", "top", "tank", "clothing", "outfit", "merch",
    }
)
GENERIC_WORDS = frozenset(
    {
        "gift", "for", "her", "him", "mom", "dad", "women", "woman", "men", "man", "kid",
        "birthday", "shirt", "tee", "tshirt", "t", "hoodie", "sweatshirt", "idea", "the", "a",
        "best", "cute", "funny", "custom", "personalized",
    }
)


@dataclass(frozen=True)
class PodFilterRules:
    blocklist: tuple[str, ...]
    allow: frozenset[str]
    # Words that may qualify a keyword that has no parent; None = same as `allow`.
    parentless_allow: frozenset[str] | None = None


def load_rules() -> PodFilterRules:
    data = load_yaml("pod_filter.yaml")
    blocklist = tuple(
        " ".join(str(t).lower().split()) for t in (data.get("blocklist") or []) if t and str(t).strip()
    )
    groups = {
        name: frozenset(str(w).lower() for w in (words or []) if w and str(w).strip())
        for name, words in (data.get("allow") or {}).items()
    }
    allow = frozenset().union(*groups.values()) if groups else frozenset()
    parentless = data.get("parentless_groups")
    parentless_allow = (
        None
        if parentless is None
        else frozenset().union(*(groups.get(str(g), frozenset()) for g in parentless))
    )
    return PodFilterRules(blocklist=blocklist, allow=allow, parentless_allow=parentless_allow)


def tokens(text: str) -> list[str]:
    return _TOKEN.findall(_POSSESSIVE.sub("", text.lower()))


def singularize(token: str) -> str:
    if len(token) > 3 and token.endswith("s") and not token.endswith(("ss", "us", "is", "as")):
        return token[:-1]
    return token


def adds_only_product_words(text: str, parent: str) -> bool:
    """True when `text` is just `parent` plus apparel/product words (or a plural)."""
    extra = {singularize(t) for t in tokens(text)} - {singularize(t) for t in tokens(parent)}
    return not (extra - APPAREL_WORDS)


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
    toks = tokens(normalized)
    for t in toks:
        if re.search(r"\d{3,}", t) and not _YEAR.fullmatch(t):
            return False
    singular = {singularize(t) for t in toks}
    if not singular or singular <= GENERIC_WORDS:
        return False
    if has_parent:
        return True
    allowed = rules.allow if rules.parentless_allow is None else rules.parentless_allow
    return bool((set(toks) | singular) & allowed)
