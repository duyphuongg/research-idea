"""Pure helpers for the Amazon lite pipeline: config, URLs, licensing, parsing, phrases."""

import re
from collections import Counter
from dataclasses import dataclass

from app.analysis.pod_filter import APPAREL_WORDS, GENERIC_WORDS
from app.config_files import load_yaml

STOPWORDS = frozenset({
    "a", "an", "and", "for", "of", "the", "to", "with", "in", "on", "my", "your", "is", "it",
    "this", "that", "i", "you", "me", "men", "mens", "women", "womens", "kids", "boys", "girls",
    "youth", "adult", "unisex",
})
_IGNORED = STOPWORDS | APPAREL_WORDS | GENERIC_WORDS

_URLS = {
    "bestsellers": "https://www.amazon.com/gp/bestsellers/fashion/{node}?pg={page}",
    "new_releases": "https://www.amazon.com/gp/new-releases/fashion/{node}?pg={page}",
}


@dataclass(frozen=True)
class AmazonCategory:
    key: str
    node: str
    product_type: str


@dataclass(frozen=True)
class AmazonConfig:
    categories: tuple[AmazonCategory, ...]
    licensed_terms: tuple[str, ...] = ()
    lists: tuple[str, ...] = ("bestsellers", "new_releases")
    pages: int = 2
    delay_seconds: tuple[float, float] = (4.0, 8.0)
    min_phrase_products: int = 3
    max_phrases: int = 40


def load_amazon_config() -> AmazonConfig:
    raw = load_yaml("amazon.yaml")
    delay = raw.get("delay_seconds", (4, 8))
    return AmazonConfig(
        categories=tuple(
            AmazonCategory(str(c["key"]), str(c["node"]), str(c["product_type"]))
            for c in raw.get("categories", [])
        ),
        lists=tuple(raw.get("lists", ("bestsellers", "new_releases"))),
        pages=int(raw.get("pages", 2)),
        delay_seconds=(float(delay[0]), float(delay[1])),
        licensed_terms=tuple(str(t).lower() for t in raw.get("licensed_terms", [])),
        min_phrase_products=int(raw.get("min_phrase_products", 3)),
        max_phrases=int(raw.get("max_phrases", 40)),
    )


def list_url(list_name: str, node: str, page: int) -> str:
    return _URLS[list_name].format(node=node, page=page)


def is_licensed(title: str, terms: tuple[str, ...] | list[str]) -> bool:
    """Whole-word / whole-phrase, case-insensitive match of any term in the title."""
    low = title.lower()
    for term in terms:
        t = term.lower().strip()
        if t and re.search(rf"(?<![a-z0-9]){re.escape(t)}(?![a-z0-9])", low):
            return True
    return False


def parse_reviews(text: str | None) -> int | None:
    if not text:
        return None
    m = re.search(r"(\d[\d,]*(?:\.\d+)?)\s*([kKmM])?", text)
    if not m:
        return None
    try:
        num = float(m.group(1).replace(",", ""))
    except ValueError:
        return None
    mult = {"k": 1_000, "m": 1_000_000}.get((m.group(2) or "").lower(), 1)
    return round(num * mult)


def parse_rating(text: str | None) -> float | None:
    if not text:
        return None
    m = re.search(r"(\d(?:\.\d)?)\s*out of\s*5", text)
    return float(m.group(1)) if m else None


def _tokens(title: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", title.lower().replace("'", ""))


def title_phrases(
    titles: list[str], min_products: int, max_phrases: int
) -> list[tuple[str, int]]:
    """2-3 word phrases counted once per title; see plan Global Constraints."""
    counts: Counter[tuple[str, ...]] = Counter()
    for title in titles:
        toks = _tokens(title)
        seen: set[tuple[str, ...]] = set()
        for n in (2, 3):
            for i in range(len(toks) - n + 1):
                gram = tuple(toks[i : i + n])
                if all(w in _IGNORED for w in gram):
                    continue
                if gram[0] in STOPWORDS or gram[-1] in STOPWORDS:
                    continue
                seen.add(gram)
        counts.update(seen)

    ranked = sorted(
        ((g, c) for g, c in counts.items() if c >= min_products),
        key=lambda gc: (-gc[1], -len(gc[0]), gc[0]),
    )
    kept: list[tuple[tuple[str, ...], int]] = []
    for gram, c in ranked:
        if len(gram) == 2 and any(
            len(k) == 3 and kc == c and (k[:2] == gram or k[1:] == gram) for k, kc in kept
        ):
            continue
        kept.append((gram, c))
    return [(" ".join(g), c) for g, c in kept[:max_phrases]]
