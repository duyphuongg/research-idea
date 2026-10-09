"""Refresh watched Etsy shops directly (one request per shop per scan), so their daily snapshots
do not depend on one of their listings being tracked."""

import logging
from datetime import date
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.connectors.etsy import shop_info_from_payload
from app.models import Shop
from app.pipeline.store import upsert_shop

logger = logging.getLogger(__name__)


class ShopClient(Protocol):
    async def get_shop(self, shop_id: int) -> dict[str, Any]: ...


async def refresh_watched_shops(session_factory: sessionmaker[Session], client: ShopClient, today: date) -> int:
    """Fetch every watched shop and upsert it with today's snapshot. Returns how many were stored.

    A failing or non-US shop is logged and skipped; nothing here raises.
    """
    try:
        with session_factory() as session:
            ids = list(session.scalars(select(Shop.id).where(Shop.watched_at.is_not(None)).order_by(Shop.id)))
    except Exception:
        logger.exception("Watched shops: could not load the watchlist")
        return 0
    stored = 0
    for shop_id in ids:
        try:
            payload = await client.get_shop(shop_id)
            info = shop_info_from_payload(payload)
            if info is None or info.shop_id != shop_id:
                logger.warning("Watched shops: shop %d skipped (not a US shop or unexpected payload)", shop_id)
                continue
            with session_factory() as session:
                upsert_shop(session, info, today)
                session.commit()
            stored += 1
        except Exception as exc:
            logger.warning("Watched shops: shop %d failed: %s: %s", shop_id, type(exc).__name__, exc)
    logger.info("Watched shops: refreshed %d/%d", stored, len(ids))
    return stored
