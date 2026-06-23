from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.analyzer.market_analytics import MarketAnalyticsService
from app.models import ApartmentStatus, ApartmentStatusHistory
from app.repositories import analytics_repo, apartment_repo, complex_repo


def _apartment_data(
    complex_id: int,
    external_id: str,
    *,
    price: int,
    price_per_sqm: float,
    district: str = "Esil",
    rooms: int = 2,
) -> dict:
    return {
        "external_id": external_id,
        "url": f"https://krisha.kz/a/show/{external_id}",
        "complex_id": complex_id,
        "price": price,
        "price_per_sqm": price_per_sqm,
        "district": district,
        "address": "Test Street",
        "rooms": rooms,
        "total_area": 100.0,
        "floor": 5,
        "total_floors": 16,
    }


async def _seed_active_apartments(
    db_session: AsyncSession,
    complex_id: int,
    *,
    suffix: str,
    base_id: int,
    district: str = "Esil",
    count: int = 5,
) -> None:
    prices = [40_000_000, 50_000_000, 60_000_000, 70_000_000, 80_000_000]
    for index in range(count):
        await apartment_repo.upsert_apartment(
            db_session,
            _apartment_data(
                complex_id,
                str(base_id + index),
                price=prices[index],
                price_per_sqm=prices[index] / 100,
                district=district,
            ),
        )


async def _create_inactive_apartment(
    db_session: AsyncSession,
    complex_id: int,
    external_id: str,
    *,
    days_on_market: int,
    days_since_deactivation: int,
    district: str = "Esil",
    rooms: int = 2,
    use_status_history: bool = True,
) -> None:
    now = datetime.now(UTC)
    deactivation = now - timedelta(days=days_since_deactivation)
    first_seen = deactivation - timedelta(days=days_on_market)

    apartment, _, _ = await apartment_repo.upsert_apartment(
        db_session,
        _apartment_data(
            complex_id,
            external_id,
            price=55_000_000,
            price_per_sqm=550_000,
            district=district,
            rooms=rooms,
        ),
    )
    apartment.is_active = False
    apartment.first_seen_at = first_seen
    apartment.last_seen_at = deactivation
    if use_status_history:
        db_session.add(
            ApartmentStatusHistory(
                apartment_id=apartment.id,
                status=ApartmentStatus.INACTIVE,
                old_price=apartment.price,
                changed_at=deactivation,
            ),
        )
    await db_session.flush()


@pytest.mark.asyncio
async def test_compute_complex_stats_returns_none_with_few_apartments(
    db_session: AsyncSession,
) -> None:
    suffix = uuid.uuid4().hex[:8]
    complex_ = await complex_repo.get_or_create(db_session, f"Few Apts {suffix}")
    service = MarketAnalyticsService(db_session)

    for index in range(4):
        await apartment_repo.upsert_apartment(
            db_session,
            _apartment_data(
                complex_.id,
                str(10_000_000 + int(suffix[:6], 16) % 1_000_000 + index),
                price=50_000_000 + index,
                price_per_sqm=500_000 + index,
            ),
        )

    assert await service.compute_complex_stats(complex_.id) is None


@pytest.mark.asyncio
async def test_compute_complex_stats_median(db_session: AsyncSession) -> None:
    suffix = uuid.uuid4().hex[:8]
    complex_ = await complex_repo.get_or_create(db_session, f"Median MA {suffix}")
    service = MarketAnalyticsService(db_session)
    prices = [40_000_000, 50_000_000, 60_000_000, 70_000_000, 80_000_000]

    base_id = 20_000_000 + int(suffix[:6], 16) % 1_000_000
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

    stats = await service.compute_complex_stats(complex_.id)
    assert stats is not None
    assert stats.median_price == 60_000_000
    assert stats.avg_price == 60_000_000
    assert stats.active_count == 5
    assert stats.complex_name == complex_.name


@pytest.mark.asyncio
async def test_compute_and_save_complex_persists_to_analytics(db_session: AsyncSession) -> None:
    suffix = uuid.uuid4().hex[:8]
    complex_ = await complex_repo.get_or_create(
        db_session,
        f"Save Complex {suffix}",
        district="Esil",
    )
    service = MarketAnalyticsService(db_session)
    prices = [40_000_000, 50_000_000, 60_000_000, 70_000_000, 80_000_000]

    base_id = 30_000_000 + int(suffix[:6], 16) % 1_000_000
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

    snapshot = await service.compute_and_save_complex(complex_.id)
    assert snapshot is not None
    assert snapshot.complex_id == complex_.id
    assert snapshot.district == "Esil"
    assert snapshot.median_price == 60_000_000
    assert snapshot.active_count == 5
    assert snapshot.sold_last_30d == 0
    assert snapshot.avg_days_on_market is None

    latest = await analytics_repo.get_latest_by_complex(db_session, complex_.id)
    assert latest is not None
    assert latest.id == snapshot.id


@pytest.mark.asyncio
async def test_compute_and_save_districts_saves_district_snapshot_with_complex_id_none(
    db_session: AsyncSession,
) -> None:
    suffix = uuid.uuid4().hex[:8]
    complex_a = await complex_repo.get_or_create(db_session, f"District A {suffix}")
    complex_b = await complex_repo.get_or_create(db_session, f"District B {suffix}")
    service = MarketAnalyticsService(db_session)
    district = f"District{int(suffix[:6], 16) % 1_000_000}"
    prices = [40_000_000, 50_000_000, 60_000_000, 70_000_000, 80_000_000]
    base_id = 40_000_000 + int(suffix[:6], 16) % 1_000_000

    for complex_ in (complex_a, complex_b):
        for index, price in enumerate(prices):
            await apartment_repo.upsert_apartment(
                db_session,
                _apartment_data(
                    complex_.id,
                    str(base_id + complex_.id * 10 + index),
                    price=price,
                    price_per_sqm=price / 100,
                    district=district,
                ),
            )

    saved = await service.compute_and_save_districts()
    assert saved >= 1

    latest = await analytics_repo.get_latest_by_district(db_session, district)
    assert latest is not None
    assert latest.complex_id is None
    assert latest.district == district
    assert latest.active_count == 10
    assert latest.median_price == 60_000_000


@pytest.mark.asyncio
async def test_compute_sale_velocity_counts_recent_inactive_and_avg_days(
    db_session: AsyncSession,
) -> None:
    suffix = uuid.uuid4().hex[:8]
    complex_ = await complex_repo.get_or_create(db_session, f"Velocity {suffix}")
    service = MarketAnalyticsService(db_session)
    base_id = 50_000_000 + int(suffix[:6], 16) % 1_000_000

    await _create_inactive_apartment(
        db_session,
        complex_.id,
        str(base_id + 1),
        days_on_market=10,
        days_since_deactivation=5,
    )
    await _create_inactive_apartment(
        db_session,
        complex_.id,
        str(base_id + 2),
        days_on_market=20,
        days_since_deactivation=15,
    )
    await _create_inactive_apartment(
        db_session,
        complex_.id,
        str(base_id + 3),
        days_on_market=40,
        days_since_deactivation=45,
    )

    velocity = await service.compute_sale_velocity(complex_.id)
    assert velocity.sold_last_30d == 2
    assert velocity.avg_days_on_market == pytest.approx((10 + 20 + 40) / 3)
    assert velocity.median_days_on_market == pytest.approx(20.0)


@pytest.mark.asyncio
async def test_compute_sale_velocity_prefers_status_history_changed_at(
    db_session: AsyncSession,
) -> None:
    suffix = uuid.uuid4().hex[:8]
    complex_ = await complex_repo.get_or_create(db_session, f"Velocity History {suffix}")
    service = MarketAnalyticsService(db_session)
    external_id = str(51_000_000 + int(suffix[:6], 16) % 1_000_000)
    now = datetime.now(UTC)
    history_deactivation = now - timedelta(days=10)
    last_seen = now - timedelta(days=60)

    apartment, _, _ = await apartment_repo.upsert_apartment(
        db_session,
        _apartment_data(
            complex_.id,
            external_id,
            price=55_000_000,
            price_per_sqm=550_000,
        ),
    )
    apartment.is_active = False
    apartment.first_seen_at = history_deactivation - timedelta(days=12)
    apartment.last_seen_at = last_seen
    db_session.add(
        ApartmentStatusHistory(
            apartment_id=apartment.id,
            status=ApartmentStatus.INACTIVE,
            old_price=apartment.price,
            changed_at=history_deactivation,
        ),
    )
    await db_session.flush()

    velocity = await service.compute_sale_velocity(complex_.id)
    assert velocity.sold_last_30d == 1
    assert velocity.avg_days_on_market == pytest.approx(12.0)


@pytest.mark.asyncio
async def test_compute_and_save_complex_persists_sale_velocity(db_session: AsyncSession) -> None:
    suffix = uuid.uuid4().hex[:8]
    complex_ = await complex_repo.get_or_create(
        db_session,
        f"Velocity Save {suffix}",
        district="Esil",
    )
    service = MarketAnalyticsService(db_session)
    base_id = 52_000_000 + int(suffix[:6], 16) % 1_000_000

    await _seed_active_apartments(
        db_session,
        complex_.id,
        suffix=suffix,
        base_id=base_id,
    )
    await _create_inactive_apartment(
        db_session,
        complex_.id,
        str(base_id + 100),
        days_on_market=10,
        days_since_deactivation=5,
    )
    await _create_inactive_apartment(
        db_session,
        complex_.id,
        str(base_id + 101),
        days_on_market=20,
        days_since_deactivation=15,
    )
    await _create_inactive_apartment(
        db_session,
        complex_.id,
        str(base_id + 102),
        days_on_market=40,
        days_since_deactivation=45,
    )

    snapshot = await service.compute_and_save_complex(complex_.id)
    assert snapshot is not None
    assert snapshot.sold_last_30d == 2
    assert snapshot.avg_days_on_market == pytest.approx((10 + 20 + 40) / 3)

    latest = await analytics_repo.get_latest_by_complex(db_session, complex_.id)
    assert latest is not None
    assert latest.sold_last_30d == 2
    assert latest.avg_days_on_market == pytest.approx((10 + 20 + 40) / 3)


@pytest.mark.asyncio
async def test_compute_and_save_districts_persists_sale_velocity(db_session: AsyncSession) -> None:
    suffix = uuid.uuid4().hex[:8]
    complex_ = await complex_repo.get_or_create(db_session, f"District Velocity {suffix}")
    service = MarketAnalyticsService(db_session)
    district = f"DistrictVel{int(suffix[:6], 16) % 1_000_000}"
    base_id = 53_000_000 + int(suffix[:6], 16) % 1_000_000

    await _seed_active_apartments(
        db_session,
        complex_.id,
        suffix=suffix,
        base_id=base_id,
        district=district,
    )
    await _create_inactive_apartment(
        db_session,
        complex_.id,
        str(base_id + 200),
        days_on_market=8,
        days_since_deactivation=3,
        district=district,
    )
    await _create_inactive_apartment(
        db_session,
        complex_.id,
        str(base_id + 201),
        days_on_market=16,
        days_since_deactivation=35,
        district=district,
    )

    saved = await service.compute_and_save_districts()
    assert saved >= 1

    latest = await analytics_repo.get_latest_by_district(db_session, district)
    assert latest is not None
    assert latest.sold_last_30d == 1
    assert latest.avg_days_on_market == pytest.approx((8 + 16) / 2)
