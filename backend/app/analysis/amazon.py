"""Pure helpers for the Amazon lite pipeline: config, URLs, licensing, parsing, phrases."""

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass

from app.analysis.pod_filter import APPAREL_WORDS, GENERIC_WORDS, singularize
from app.config_files import load_yaml

STOPWORDS = frozenset({
    "a", "an", "and", "for", "of", "the", "to", "with", "in", "on", "my", "your", "is", "it",
    "this", "that", "i", "you", "me", "men", "mens", "women", "womens", "kids", "boys", "girls",
    "youth", "adult", "unisex",
    "we", "our", "us", "be", "are", "so", "just", "all", "who", "what",
})
_APPAREL_IGNORED = APPAREL_WORDS | frozenset(
    {"top", "tee", "shirt", "tshirt", "t", "sweatshirt", "hoodie"}
)
# Descriptor adjectives stay usable at a phrase edge ("funny pickleball").
_DESCRIPTORS = frozenset({"best", "cute", "funny", "custom", "personalized"})
_IGNORED = STOPWORDS | APPAREL_WORDS | (GENERIC_WORDS - _DESCRIPTORS) | frozenset(
    {"top", "tee", "shirt", "tshirt", "t", "sweatshirt", "hoodie", "gift"}
)

_DESCRIPTOR_IGNORED = frozenset({
    "sleeve", "sleeves", "long", "short", "crew", "neck", "crewneck", "pullover", "graphic",
    "oversized", "oversize", "fit", "fitted", "loose", "cotton", "soft", "casual", "raglan",
    "vneck", "v", "blouse", "blouses", "tunic", "tank", "tops", "top", "jersey", "baseball",
    "quarter", "zip", "hooded", "lightweight", "heavyweight", "plus", "size",
})
_IGNORED = _IGNORED | _DESCRIPTOR_IGNORED
_APPAREL_IGNORED = _APPAREL_IGNORED | _DESCRIPTOR_IGNORED
PAGE_SIZE = 50

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
    non_pod_terms: tuple[str, ...] = ()
    phrase_ignore_words: tuple[str, ...] = ()
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
        non_pod_terms=tuple(str(t).lower() for t in raw.get("non_pod_terms", [])),
        phrase_ignore_words=tuple(str(t).lower() for t in raw.get("phrase_ignore_words", [])),
        min_phrase_products=int(raw.get("min_phrase_products", 3)),
        max_phrases=int(raw.get("max_phrases", 40)),
    )


def list_url(list_name: str, node: str, page: int) -> str:
    return _URLS[list_name].format(node=node, page=page)


def _norm_license(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", re.sub(r"[-/.'\u2019]", " ", text)).strip()


def is_licensed(title: str, terms: tuple[str, ...] | list[str]) -> bool:
    """Whole-word / whole-phrase, case-insensitive match of any term in the title."""
    low = _norm_license(title)
    for term in terms:
        t = _norm_license(term)
        if t and re.search(rf"(?<![a-z0-9]){re.escape(t)}(?![a-z0-9])", low):
            return True
    return False


def is_non_pod(title: str, terms: tuple[str, ...] | list[str]) -> bool:
    """Same whole-phrase matching as is_licensed, for blank/multipack/non-POD listings."""
    return is_licensed(title, terms)


def parse_reviews(text: str | None) -> int | None:
    if not text:
        return None
    m = re.match(r"^\(?\s*([\d,]+(?:\.\d+)?)\s*([kKmM])?\s*\)?$", text.strip())
    if not m:
        return None
    suffix = (m.group(2) or "").lower()
    if "." in m.group(1) and not suffix:
        return None
    try:
        num = float(m.group(1).replace(",", ""))
    except ValueError:
        return None
    return round(num * {"k": 1_000, "m": 1_000_000}.get(suffix, 1))


def parse_rating(text: str | None) -> float | None:
    if not text:
        return None
    m = re.search(r"(?<![\d.])(\d(?:\.\d)?)\s*out of\s*5", text)
    return float(m.group(1)) if m else None


_SEGMENT_SPLIT = re.compile(r"[|,()/:;]| - ")


def _segments(title: str) -> list[list[str]]:
    out = []
    for seg in _SEGMENT_SPLIT.split(title.lower().replace("\u2019", "'")):
        toks = re.findall(r"[a-z0-9]+", seg.replace("'", ""))
        if toks:
            out.append(toks)
    return out


def title_phrases(
    titles: list[str],
    min_products: int,
    max_phrases: int,
    ignore_words: tuple[str, ...] | list[str] = (),
) -> list[tuple[str, int]]:
    """2-3 word phrases counted once per title; see plan Global Constraints."""
    extra = frozenset(w.lower() for w in ignore_words)
    counts: Counter[tuple[str, ...]] = Counter()
    occurrences: Counter[tuple[str, ...]] = Counter()
    for title in titles:
        seen: set[tuple[str, ...]] = set()
        occ: Counter[tuple[str, ...]] = Counter()
        for toks in _segments(title):
            for n in (2, 3):
                for i in range(len(toks) - n + 1):
                    gram = tuple(toks[i : i + n])
                    if any(
                        singularize(w) in _APPAREL_IGNORED or w in _APPAREL_IGNORED
                        or singularize(w) in extra or w in extra
                        for w in gram
                    ):
                        continue
                    if any(
                        (w in STOPWORDS or singularize(w) in STOPWORDS)
                        and not (n == 3 and j == 1 and w in ("of", "and"))
                        for j, w in enumerate(gram)
                    ):
                        continue
                    ign = [singularize(w) in _IGNORED or w in _IGNORED for w in gram]
                    if ign[0] or ign[-1] or sum(ign) * 2 >= len(gram):
                        continue
                    seen.add(gram)
                    occ[gram] += 1
        counts.update(seen)
        occurrences.update(occ)

    ranked = sorted(
        ((g, c) for g, c in counts.items() if c >= min_products),
        key=lambda gc: (-gc[1], -len(gc[0]), gc[0]),
    )
    kept: list[tuple[tuple[str, ...], int]] = []
    for gram, c in ranked:
        if len(gram) == 2 and any(
            len(k) == 3
            and kc == c
            and occurrences[k] >= occurrences[gram]
            and (k[:2] == gram or k[1:] == gram)
            for k, kc in kept
        ):
            continue
        kept.append((gram, c))
    return [(" ".join(g), c) for g, c in kept[:max_phrases]]
