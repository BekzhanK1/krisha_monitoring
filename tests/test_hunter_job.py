from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analyzer.deal_analyzer import clear_market_stats_cache
from app.models import Notification
from app.repositories import apartment_repo, complex_repo
from app.scheduler import hunter_job as hunter_job_module
from app.scheduler.hunter_job import get_hunter_job_status, hunter_job
from app.scraper.filters import SearchFilters
from app.telegram.notifications import NOTIFICATION_TYPE_HUNTER_ALERT


def _apartment_data(
    complex_id: int,
    external_id: str,
    *,
    price: int,
    price_per_sqm: float,
    description: str | None = None,
) -> dict:
    return {
        "external_id": external_id,
        "url": f"https://krisha.kz/a/show/{external_id}",
        "complex_id": complex_id,
        "price": price,
        "price_per_sqm": price_per_sqm,
        "district": "Esil",
        "address": "Kabanbay 12",
        "rooms": 2,
        "total_area": 100.0,
        "floor": 5,
        "total_floors": 16,
        "description": description,
    }


@pytest.fixture(autouse=True)
def reset_hunter_job_state() -> None:
    clear_market_stats_cache()
    hunter_job_module._hunter_running = False
    hunter_job_module._last_hunter_run = None
    yield
    clear_market_stats_cache()
    hunter_job_module._hunter_running = False
    hunter_job_module._last_hunter_run = None


@pytest.fixture
def permissive_filters():
    with patch(
        "app.scheduler.hunter_job._get_active_filters",
        new_callable=AsyncMock,
    ) as mock_filters:
        mock_filters.return_value = SearchFilters()
        yield mock_filters


@pytest.fixture
def patch_hunter_session(db_session: AsyncSession):
    with patch("app.scheduler.hunter_job.AsyncSessionLocal") as session_local:
        session_local.return_value.__aenter__ = AsyncMock(return_value=db_session)
        session_local.return_value.__aexit__ = AsyncMock(return_value=False)
        yield db_session


@pytest.fixture
def telegram_settings():
    with patch("app.scheduler.hunter_job.get_settings") as mock_settings:
        settings = mock_settings.return_value
        settings.hunter_interval_minutes = 30
        settings.telegram_bot_token = "test-token"
        settings.telegram_chat_id = 12345
        yield settings


async def _seed_market_with_hunter_target(db_session: AsyncSession) -> tuple[str, str]:
    suffix = uuid.uuid4().hex[:8]
    complex_ = await complex_repo.get_or_create(db_session, f"Residential {suffix}")
    prices = [40_000_000, 50_000_000, 60_000_000, 70_000_000, 80_000_000]
    base_id = 140_000_000 + int(suffix[:6], 16) % 1_000_000

    old_seen_at = datetime.now(UTC) - timedelta(days=7)

    for index, price in enumerate(prices):
        apartment, _, _ = await apartment_repo.upsert_apartment(
            db_session,
            _apartment_data(
                complex_.id,
                str(base_id + index),
                price=price,
                price_per_sqm=price / 100,
            ),
        )
        apartment.first_seen_at = old_seen_at

    hunter_id = str(base_id + 100)
    hunter_apartment, _, _ = await apartment_repo.upsert_apartment(
        db_session,
        _apartment_data(
            complex_.id,
            hunter_id,
            price=35_000_000,
            price_per_sqm=350_000,
            description="Срочная продажа, торг уместен",
        ),
    )
    hunter_apartment.first_seen_at = datetime.now(UTC)
    await db_session.flush()
    return hunter_id, suffix


@pytest.mark.asyncio
async def test_hunter_job_sends_alert_for_urgent_deal(
    patch_hunter_session: AsyncSession,
    telegram_settings,
    permissive_filters,
) -> None:
    db_session = patch_hunter_session
    hunter_id, _ = await _seed_market_with_hunter_target(db_session)

    sender = AsyncMock(return_value=True)
    with patch("app.telegram.notifications.send_alert", sender):
        await hunter_job()

    status = get_hunter_job_status()
    assert status is not None
    assert status["status"] == "success"
    assert status["candidates_found"] >= 1
    assert status["alerts_sent"] == 1
    sender.assert_awaited_once()

    apartment = await apartment_repo.get_by_external_id(db_session, hunter_id)
    assert apartment is not None
    result = await db_session.execute(
        select(Notification).where(
            Notification.apartment_id == apartment.id,
            Notification.notification_type == NOTIFICATION_TYPE_HUNTER_ALERT,
        ),
    )
    notification = result.scalar_one()
    assert notification.is_sent is True
    assert "Срочная сделка" in notification.message


@pytest.mark.asyncio
async def test_hunter_job_dedupes_repeat_alerts(
    patch_hunter_session: AsyncSession,
    telegram_settings,
    permissive_filters,
) -> None:
    db_session = patch_hunter_session
    await _seed_market_with_hunter_target(db_session)

    sender = AsyncMock(return_value=True)
    with patch("app.telegram.notifications.send_alert", sender):
        await hunter_job()
        await hunter_job()

    assert sender.await_count == 1

    status = get_hunter_job_status()
    assert status is not None
    assert status["alerts_sent"] == 0


@pytest.mark.asyncio
async def test_hunter_job_respects_search_config_filters(
    patch_hunter_session: AsyncSession,
    telegram_settings,
) -> None:
    db_session = patch_hunter_session
    await _seed_market_with_hunter_target(db_session)

    restrictive = SearchFilters(price_to=30_000_000)
    sender = AsyncMock(return_value=True)
    with (
        patch(
            "app.scheduler.hunter_job._get_active_filters",
            new_callable=AsyncMock,
            return_value=restrictive,
        ),
        patch("app.telegram.notifications.send_alert", sender),
    ):
        await hunter_job()

    status = get_hunter_job_status()
    assert status is not None
    assert status["candidates_found"] == 0
    sender.assert_not_awaited()


@pytest.mark.asyncio
async def test_hunter_job_parallel_guard_skips_second_call() -> None:
    hunter_job_module._hunter_running = True

    with patch("app.scheduler.hunter_job._find_hunter_candidates") as find_candidates:
        await hunter_job()
        find_candidates.assert_not_called()

    assert get_hunter_job_status() is None
