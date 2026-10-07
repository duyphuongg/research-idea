from collections.abc import Callable

from app.config import Settings
from app.connectors.base import Connector
from app.connectors.amazon import AmazonConnector
from app.connectors.etsy import EtsyConnector
from app.connectors.google_daily import GoogleDailyTrendsConnector
from app.connectors.google_suggest import GoogleSuggestConnector

ConnectorFactory = Callable[[Settings, dict[str, bool], list[str] | None], list[Connector]]


def make_all_connectors(settings: Settings) -> list[Connector]:
    return [
        EtsyConnector(api_key=settings.etsy_api_key),
        GoogleSuggestConnector(),
        GoogleDailyTrendsConnector(),
        AmazonConnector(),
    ]


def build_connectors(
    settings: Settings, enabled_overrides: dict[str, bool], only: list[str] | None = None
) -> list[Connector]:
    return [
        c
        for c in make_all_connectors(settings)
        if c.enabled()
        and enabled_overrides.get(c.name, True)
        and (only is None or c.name in only)
    ]


def connector_status(settings: Settings, enabled_overrides: dict[str, bool]) -> list[dict]:
    statuses = [
        {
            "name": c.name,
            "kind": c.kind,
            "configured": c.enabled(),
            "enabled": enabled_overrides.get(c.name, True),
        }
        for c in make_all_connectors(settings)
    ]
    statuses.append(
        {
            "name": "etsy_signals",
            "kind": "signals",
            "configured": bool(settings.etsy_api_key),
            "enabled": enabled_overrides.get("etsy_signals", True),
        }
    )
    return statuses
