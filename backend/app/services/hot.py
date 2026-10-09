"""Velocity and hot flags for Best Sellers products (shared by the products API and alerts)."""

from dataclasses import dataclass

from sqlalchemy import exists, select
from sqlalchemy.orm import Session, selectinload

from app.analysis.product_type import is_digital_listing
from app.analysis.velocity import SnapshotPoint, compute_velocity, hot_ids, velocity_metric
from app.models import ListingSignal, Product, ProductKeyword


@dataclass(frozen=True)
class ProductMetrics:
    delta_7d: float | None
    velocity: float | None
    metric: str | None
    hot: bool


def compute_product_metrics(session: Session) -> tuple[list[Product], dict[int, ProductMetrics]]:
    """Best Sellers population: products not only tracked by Listing Signals, or linked to a keyword.

    Etsy design files/transfers stored before the digital filter existed are left out, and so are
    Amazon products kept in the DB from when Amazon was still scanned.
    """
    products = [p for p in session.scalars(
        select(Product)
        .where(Product.source != "amazon")
        .where(
            ~exists().where(ListingSignal.product_id == Product.id)
            | exists().where(ProductKeyword.product_id == Product.id)
        )
        .order_by(Product.id)
        .options(selectinload(Product.snapshots))
    ) if not (p.source == "etsy" and is_digital_listing(p.title))]
    points = {
        p.id: [SnapshotPoint(s.date, s.reviews, s.favorites, s.views) for s in p.snapshots] for p in products
    }
    velocities = {
        p.id: compute_velocity(points[p.id], p.listed_at.date() if p.listed_at else None) for p in products
    }
    hot = hot_ids((p.id, (p.source, p.product_type), velocities[p.id][1]) for p in products if not p.licensed)
    return products, {
        p.id: ProductMetrics(velocities[p.id][0], velocities[p.id][1], velocity_metric(points[p.id]), p.id in hot)
        for p in products
    }
