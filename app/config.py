from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


class Settings(BaseSettings):
    database_url: str
    telegram_bot_token: str = ""
    telegram_chat_id: int = 0
    parser_interval_minutes: int = 30
    hunter_interval_minutes: int = 30
    run_analytics_after_scrape: bool = True
    run_scoring_after_analytics: bool = True
    scraper_max_listings: int | None = None
    renovation_per_sqm: int = 150_000
    transaction_fee_pct: float = 0.01
    capital_gains_tax_pct: float = 0.10
    log_level: str = "INFO"
    environment: Literal["development", "production"] = "development"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("scraper_max_listings", mode="before")
    @classmethod
    def normalize_scraper_max_listings(cls, value: object) -> int | None:
        if value in ("", None):
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            return int(value)
        msg = "SCRAPER_MAX_LISTINGS must be an integer"
        raise ValueError(msg)

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        normalized = value.replace(":///", "://", 1) if ":///" in value else value
        url = make_url(normalized)
        if url.host is None:
            msg = (
                "DATABASE_URL must include a host, e.g. postgresql+asyncpg://user:pass@host:5432/db"
            )
            raise ValueError(msg)
        return normalized


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
