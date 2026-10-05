import re
from typing import Literal

ProductType = Literal["tshirt", "sweatshirt", "hoodie", "other"]

_PATTERNS: dict[str, re.Pattern[str]] = {
    "hoodie": re.compile(r"\b(hoodies?|hooded)\b"),
    "sweatshirt": re.compile(r"\b(sweatshirts?|crew ?necks?)\b"),
    "tshirt": re.compile(r"\b(t-?shirts?|tees?|shirts?)\b"),
}


def classify_product_type(title: str) -> ProductType:
    """Classify by the apparel word that appears first in the title."""
    text = title.lower()
    best: tuple[int, ProductType] | None = None
    for product_type, pattern in _PATTERNS.items():
        match = pattern.search(text)
        if match and (best is None or match.start() < best[0]):
            best = (match.start(), product_type)  # type: ignore[assignment]
    return best[1] if best else "other"
