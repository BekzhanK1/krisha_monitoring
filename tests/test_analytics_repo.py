from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ResidentialComplex
from app.repositories import analytics_repo


def _snapshot_data(**overrides: object) -> dict:
    base = {
        "median_price": 25_000_000,
        "avg_price": 26_000_000,
        "median_price_per_sqm": 350_000,
        "avg_price_per_sqm": 360_000.5,
        "active_count": 12,
        "sold_last_30d": 3,
        "avg_days_on_market": 45.5,
    }
    base.update(overrides)
    return base


@pytest.mark.asyncio
async def test_save_snapshot_and_get_latest_by_complex(db_session: AsyncSession) -> None:
    complex_ = ResidentialComplex(name="Test Complex", district="Esil")
    db_session.add(complex_)
    await db_session.flush()

    older = await analytics_repo.save_snapshot(
        db_session,
        _snapshot_data(
            complex_id=complex_.id,
            active_count=10,
            calculated_at=datetime(2026, 1, 1, tzinfo=UTC),
        ),
    )
    newer = await analytics_repo.save_snapshot(
        db_session,
        _snapshot_data(
            complex_id=complex_.id,
            active_count=15,
            calculated_at=datetime(2026, 6, 1, tzinfo=UTC),
        ),
    )

    latest = await analytics_repo.get_latest_by_complex(db_session, complex_.id)
    assert latest is not None
    assert latest.id == newer.id
    assert latest.active_count == 15
    assert latest.id != older.id


@pytest.mark.asyncio
async def test_get_latest_by_complex_filters_by_rooms(db_session: AsyncSession) -> None:
    complex_ = ResidentialComplex(name="Rooms Complex", district="Esil")
    db_session.add(complex_)
    await db_session.flush()

    await analytics_repo.save_snapshot(
        db_session,
        _snapshot_data(
            complex_id=complex_.id,
            rooms=2,
            active_count=8,
            calculated_at=datetime(2026, 6, 1, tzinfo=UTC),
        ),
    )
    three_room = await analytics_repo.save_snapshot(
        db_session,
        _snapshot_data(
            complex_id=complex_.id,
            rooms=3,
            active_count=5,
            calculated_at=datetime(2026, 5, 1, tzinfo=UTC),
        ),
    )

    latest = await analytics_repo.get_latest_by_complex(db_session, complex_.id, rooms=3)
    assert latest is not None
    assert latest.id == three_room.id
    assert latest.rooms == 3


@pytest.mark.asyncio
async def test_get_latest_by_district(db_session: AsyncSession) -> None:
    await analytics_repo.save_snapshot(
        db_session,
        _snapshot_data(
            district="Esil",
            active_count=20,
            calculated_at=datetime(2026, 1, 1, tzinfo=UTC),
        ),
    )
    newer = await analytics_repo.save_snapshot(
        db_session,
        _snapshot_data(
            district="Esil",
            active_count=25,
            calculated_at=datetime(2026, 6, 1, tzinfo=UTC),
        ),
    )
    await analytics_repo.save_snapshot(
        db_session,
        _snapshot_data(
            complex_id=None,
            district="Almaty",
            active_count=99,
            calculated_at=datetime(2026, 6, 2, tzinfo=UTC),
        ),
    )

    latest = await analytics_repo.get_latest_by_district(db_session, "Esil")
    assert latest is not None
    assert latest.id == newer.id
    assert latest.complex_id is None
    assert latest.district == "Esil"


@pytest.mark.asyncio
async def test_get_history_filters_by_days(db_session: AsyncSession) -> None:
    complex_ = ResidentialComplex(name="History Complex", district="Esil")
    db_session.add(complex_)
    await db_session.flush()

    now = datetime.now(UTC)
    await analytics_repo.save_snapshot(
        db_session,
        _snapshot_data(
            complex_id=complex_.id,
            active_count=10,
            calculated_at=now - timedelta(days=10),
        ),
    )
    await analytics_repo.save_snapshot(
        db_session,
        _snapshot_data(
            complex_id=complex_.id,
            active_count=11,
            calculated_at=now - timedelta(days=100),
        ),
    )

    history = await analytics_repo.get_history(db_session, complex_.id, days=30)
    assert len(history) == 1
    assert history[0].active_count == 10

    full_history = await analytics_repo.get_history(db_session, complex_.id, days=365)
    assert len(full_history) == 2
