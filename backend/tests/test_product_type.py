import pytest

from app.analysis.product_type import classify_product_type


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
