from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories import apartment_repo, complex_repo, score_repo
from app.scheduler import jobs as jobs_module
from app.scheduler.jobs import get_scoring_job_status, scoring_job


def _apartment_data(
    complex_id: int,
    external_id: str,
    *,
    price: int,
    price_per_sqm: float,
) -> dict:
    return {
        "external_id": external_id,
        "url": f"https://krisha.kz/a/show/{external_id}",
        "complex_id": complex_id,
        "price": price,
        "price_per_sqm": price_per_sqm,
        "district": "Esil",
        "address": "Test Street",
        "rooms": 2,
        "total_area": 100.0,
        "floor": 5,
        "total_floors": 16,
    }


@pytest.fixture(autouse=True)
def reset_scoring_job_state() -> None:
    jobs_module._scoring_running = False
    jobs_module._last_scoring_run = None
    yield
    jobs_module._scoring_running = False
    jobs_module._last_scoring_run = None


@pytest.fixture
def patch_scoring_session(db_session: AsyncSession):
    with patch("app.scheduler.jobs.AsyncSessionLocal") as session_local:
        session_local.return_value.__aenter__ = AsyncMock(return_value=db_session)
        session_local.return_value.__aexit__ = AsyncMock(return_value=False)
        yield db_session


@pytest.mark.asyncio
async def test_scoring_job_scores_active_apartments(
    patch_scoring_session: AsyncSession,
) -> None:
    db_session = patch_scoring_session
    suffix = uuid.uuid4().hex[:8]
    complex_ = await complex_repo.get_or_create(db_session, f"Scoring Job Complex {suffix}")
    prices = [40_000_000, 50_000_000, 60_000_000, 70_000_000, 80_000_000]
    base_id = 130_000_000 + int(suffix[:6], 16) % 1_000_000
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

    await scoring_job()

    status = get_scoring_job_status()
    assert status is not None
    assert status["status"] == "success"
    assert status["apartments_scored"] == 5

    first_apartment = await apartment_repo.get_by_external_id(db_session, str(base_id))
    assert first_apartment is not None
    score = await score_repo.get_by_apartment_id(db_session, first_apartment.id)
    assert score is not None


@pytest.mark.asyncio
async def test_scoring_job_parallel_guard_skips_second_call() -> None:
    jobs_module._scoring_running = True

    with patch("app.scheduler.jobs.score_all_active") as score_all:
        await scoring_job()
        score_all.assert_not_called()

    assert get_scoring_job_status() is None
