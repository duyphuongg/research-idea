import pytest

from app.analysis.product_type import classify_product_type, is_digital_listing


@pytest.mark.parametrize(
    "title,expected",
    [
        ("Funny Nurse Shirt, Nurse Hoodie", "tshirt"),  # earliest mention wins
        ("Retro Dog Mom Sweatshirt", "sweatshirt"),
        ("Fishing Hooded Sweatshirt", "hoodie"),
        ("Comfort Colors Teacher Tee", "tshirt"),
        ("Christmas T-Shirt for Family", "tshirt"),
        ("Halloween Crewneck", "sweatshirt"),
        ("Pickleball HOODIES Gift", "hoodie"),
        ("Nurse Coffee Mug", "other"),
        ("Teepee Tent Decor", "other"),
    ],
)
def test_classify_product_type(title, expected):
    assert classify_product_type(title) == expected


@pytest.mark.parametrize(
    "title,listing_type,expected",
    [
        ("Thriller Night PNG, Halloween Horror PNG, Halloween Shirt", "physical", True),
        ("Spooky Ghost SVG PNG, Girly Halloween Shirt Design", None, True),
        ("Nurse Halloween Shirt Design, Digital Download", None, True),
        ("Retro Cow Sublimation Design | Cow Lover Shirt Graphic", None, True),
        ("Blue Dog Mom Shirt Mockup: Canva Template", None, True),
        ("Game Day Football DTF Transfer, Ready to Press", None, True),
        ("Football Mom Shirt", "download", True),
        ("Football Mom Shirt", "both", False),
        ("Game Day Football Mom Comfort Colors Shirt", "physical", False),
        ("Pickleball Png Lover Tee", None, True),
        ("Spongebob Squarepants Shirt", None, False),  # 'png' only as a whole word
    ],
)
def test_is_digital_listing(title, listing_type, expected):
    assert is_digital_listing(title, listing_type) is expected
