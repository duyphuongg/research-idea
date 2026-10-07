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


# Design files, mockups and heat transfers sold as "shirt" listings — not garments.
_DIGITAL = re.compile(
    r"\b(png|svg|dxf|eps|clipart|mockups?|digital download|instant download|digital file"
    r"|sublimation (design|graphic|png|file)s?|canva template|dtf transfers?|iron[- ]on transfers?"
    r"|ready to press)\b"
)


def is_digital_listing(title: str, listing_type: str | None = None) -> bool:
    """True for Etsy listings that sell a file or transfer instead of a printed garment."""
    return listing_type == "download" or bool(_DIGITAL.search(title.lower()))
