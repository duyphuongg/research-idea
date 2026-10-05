from datetime import date, datetime

from app.connectors.base import NormalizedBatch, NormalizedProduct, RawBatch


def make_product(**overrides) -> NormalizedProduct:
    values = dict(
        source="fake",
        external_id="1",
        title="Nurse Shirt",
        url="https://example.com/1",
        image_url=None,
        shop_name="Shop",
        price=19.99,
        currency="USD",
        product_type="tshirt",
        listed_at=datetime(2026, 9, 1),
        keyword="nurse",
        rank=1,
        favorites=10,
    )
    values.update(overrides)
    return NormalizedProduct(**values)


class FakeConnector:
    kind = "product"

    def __init__(self, name="fake", products=None, errors=None, fail=False):
        self.name = name
        self.products = [make_product()] if products is None else products
        self.errors = errors or []
        self.fail = fail
        self.received_keywords: list[str] | None = None

    def enabled(self) -> bool:
        return True

    async def fetch(self, keywords: list[str]) -> RawBatch:
        self.received_keywords = list(keywords)
        if self.fail:
            raise RuntimeError("boom")
        return RawBatch(source=self.name, payloads=[{"keywords": list(keywords)}], errors=list(self.errors))

    def normalize(self, raw: RawBatch, today: date) -> NormalizedBatch:
        return NormalizedBatch(products=list(self.products))
