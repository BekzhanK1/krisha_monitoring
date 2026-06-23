from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories import analytics_repo, apartment_repo, complex_repo
from app.scheduler import jobs as jobs_module
from app.scheduler.jobs import analytics_job, get_analytics_job_status


def _apartment_data(
    complex_id: int,
    external_id: str,
    *,
    price: int,
    price_per_sqm: float,
    district: str = "Esil",
) -> dict:
    return {
        "external_id": external_id,
        "url": f"https://krisha.kz/a/show/{external_id}",
        "complex_id": complex_id,
        "price": price,
        "price_per_sqm": price_per_sqm,
        "district": district,
        "address": "Test Street",
        "rooms": 2,
        "total_area": 100.0,
        "floor": 5,
        "total_floors": 16,
    }


@pytest.fixture(autouse=True)
def reset_analytics_job_state() -> None:
    jobs_module._analytics_running = False
    jobs_module._last_analytics_run = None
    yield
    jobs_module._analytics_running = False
    jobs_module._last_analytics_run = None


@pytest.fixture
def patch_analytics_session(db_session: AsyncSession):
    with patch("app.scheduler.jobs.AsyncSessionLocal") as session_local:
        session_local.return_value.__aenter__ = AsyncMock(return_value=db_session)
        session_local.return_value.__aexit__ = AsyncMock(return_value=False)
        yield db_session


@pytest.mark.asyncio
async def test_analytics_job_computes_and_saves(patch_analytics_session: AsyncSession) -> None:
    db_session = patch_analytics_session
    suffix = uuid.uuid4().hex[:8]
    complex_ = await complex_repo.get_or_create(
        db_session,
        f"Analytics Job Complex {suffix}",
        district="Esil",
    )
    prices = [40_000_000, 50_000_000, 60_000_000, 70_000_000, 80_000_000]
    base_id = 50_000_000 + int(suffix[:6], 16) % 1_000_000
    for index, price in enumerate(prices):
        await apartment_repo.upsert_apartment(
            db_session,
            _apartment_data(
                complex_.id,
                str(base_id + index),
                price=price,
                price_per_sqm=price / 100,
            ),
        )
    await db_session.flush()

    await analytics_job()

    latest = await analytics_repo.get_latest_by_complex(db_session, complex_.id)
    assert latest is not None
    assert latest.active_count == 5
    assert latest.median_price == 60_000_000

    status = get_analytics_job_status()
    assert status is not None
    assert status["status"] == "success"
    assert status["complex_snapshots"] >= 1
    assert status["district_snapshots"] >= 1


@pytest.mark.asyncio
async def test_analytics_job_parallel_guard_skips_second_call() -> None:
    jobs_module._analytics_running = True

    with patch(
        "app.scheduler.jobs.MarketAnalyticsService",
    ) as service_cls:
        await analytics_job()
        service_cls.assert_not_called()

    assert get_analytics_job_status() is None


@pytest.mark.asyncio
async def test_get_analytics_job_status_after_successful_run(
    patch_analytics_session: AsyncSession,
) -> None:
    db_session = patch_analytics_session
    suffix = uuid.uuid4().hex[:8]
    complex_ = await complex_repo.get_or_create(db_session, f"Status Complex {suffix}")
    prices = [40_000_000, 50_000_000, 60_000_000, 70_000_000, 80_000_000]
    base_id = 60_000_000 + int(suffix[:6], 16) % 1_000_000
    for index, price in enumerate(prices):
        await apartment_repo.upsert_apartment(
            db_session,
            _apartment_data(
                complex_.id,
                str(base_id + index),
                price=price,
                price_per_sqm=price / 100,
            ),
        )
    await db_session.flush()

    await analytics_job()

    status = get_analytics_job_status()
    assert status is not None
    assert status["status"] == "success"
    assert isinstance(status["last_run"], str)
    assert status["complex_snapshots"] >= 1
    assert status["district_snapshots"] >= 1
    assert isinstance(status["duration_sec"], float)
    assert status["duration_sec"] >= 0
