from datetime import datetime

from pydantic import BaseModel


class ProductOut(BaseModel):
    id: int
    source: str
    title: str
    url: str
    image_url: str | None
    shop_name: str | None
    price: float | None
    currency: str | None
    product_type: str
    listed_at: datetime | None
    reviews: int | None
    favorites: int | None
    rating: float | None
    delta_7d: float | None
    velocity: float | None
    hot: bool
    keywords: list[str]


class ProductPage(BaseModel):
    total: int
    items: list[ProductOut]
