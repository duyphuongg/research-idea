from app.analysis import alerts as alerts_mod
from app.analysis.alerts import AlertsConfig, load_alerts_config
from app.config import Settings


def test_defaults_match_yaml():
    assert load_alerts_config() == AlertsConfig(
        niche_min_score=60, niche_min_growth=0.20, amazon_top_n=20, cooldown_days=7, telegram_max_items=5
    )


def test_missing_file_gives_defaults(monkeypatch):
    monkeypatch.setattr(alerts_mod, "load_yaml", lambda name: {})
    assert load_alerts_config() == AlertsConfig()


def test_telegram_settings_default_none():
    s = Settings(_env_file=None)
    assert s.telegram_bot_token is None and s.telegram_chat_id is None and s.app_url is None
