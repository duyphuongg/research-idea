"""Alert rules: which niches/products are worth telling the user about after a scan."""

from dataclasses import dataclass, fields

from app.config_files import load_yaml


@dataclass(frozen=True)
class AlertsConfig:
    niche_min_score: float = 60
    niche_min_growth: float = 0.20
    amazon_top_n: int = 20
    cooldown_days: int = 7
    telegram_max_items: int = 5


def load_alerts_config() -> AlertsConfig:
    data = load_yaml("alerts.yaml")
    kwargs = {}
    for f in fields(AlertsConfig):
        if f.name in data:
            kwargs[f.name] = int(data[f.name]) if f.type in (int, "int") else float(data[f.name])
    return AlertsConfig(**kwargs)
