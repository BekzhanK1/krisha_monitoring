from pathlib import Path

import pytest

from app.config import get_settings
from app.logging_config import setup_logging


@pytest.fixture(autouse=True)
def clear_settings_cache() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_setup_logging_runs_without_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:pass@host:5432/db")
    monkeypatch.chdir(tmp_path)

    setup_logging()
