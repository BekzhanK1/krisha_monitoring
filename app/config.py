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
    log_level: str = "INFO"
    environment: Literal["development", "production"] = "development"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        normalized = value.replace(":///", "://", 1) if ":///" in value else value
        url = make_url(normalized)
        if url.host is None:
            msg = (
                "DATABASE_URL must include a host, e.g. "
                "postgresql+asyncpg://user:pass@host:5432/db"
            )
            raise ValueError(msg)
        return normalized


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
