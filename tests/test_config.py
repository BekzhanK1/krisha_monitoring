from pathlib import Path

import pytest

from app.config import Settings, get_settings


@pytest.fixture(autouse=True)
def clear_settings_cache() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_settings_loads_from_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:pass@host:5432/db")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")
    monkeypatch.setenv("PARSER_INTERVAL_MINUTES", "15")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("ENVIRONMENT", "production")

    settings = Settings()

    assert settings.database_url == "postgresql+asyncpg://user:pass@host:5432/db"
    assert settings.telegram_bot_token == "test-token"
    assert settings.telegram_chat_id == 12345
    assert settings.parser_interval_minutes == 15
    assert settings.log_level == "DEBUG"
    assert settings.environment == "production"


def test_get_settings_returns_same_instance(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:pass@host:5432/db")

    first = get_settings()
    second = get_settings()

    assert first is second
