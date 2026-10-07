from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "sqlite:///./data/radar.db"
    etsy_api_key: str | None = None
    scheduler_enabled: bool = True
    raw_retention_days: int = 30
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    app_url: str | None = None  # e.g. http://<mac>.<tailnet>.ts.net:3737 — used for links in Telegram
    cors_origins: list[str] = ["http://localhost:3737"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
