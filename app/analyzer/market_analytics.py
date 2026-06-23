from __future__ import annotations

import statistics
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analyzer.deal_analyzer import MIN_ACTIVE_APARTMENTS, MarketStats
from app.analyzer.types import SaleVelocity
from app.models import (
    Apartment,
    ApartmentStatus,
    ApartmentStatusHistory,
    MarketAnalytics,
    ResidentialComplex,
)
from app.repositories import analytics_repo, apartment_repo, complex_repo

SECONDS_PER_DAY = 86_400
SOLD_WINDOW_DAYS = 30


def _calculate_stats(
    apartments: list[Apartment],
    *,
    complex_id: int,
    complex_name: str,
) -> MarketStats | None:
    if len(apartments) < MIN_ACTIVE_APARTMENTS:
        return None

    prices = [apartment.price for apartment in apartments]
    prices_per_sqm = [apartment.price_per_sqm for apartment in apartments]
    return MarketStats(
        complex_id=complex_id,
        complex_name=complex_name,
        median_price=int(statistics.median(prices)),
        avg_price=int(statistics.mean(prices)),
        median_price_per_sqm=int(statistics.median(prices_per_sqm)),
        avg_price_per_sqm=int(statistics.mean(prices_per_sqm)),
        active_count=len(apartments),
        calculated_at=datetime.now(UTC),
    )


def _snapshot_from_stats(
    stats: MarketStats,
    *,
    complex_id: int | None,
    district: str | None,
    rooms: int | None,
    velocity: SaleVelocity | None = None,
) -> dict[str, object]:
    return {
        "complex_id": complex_id,
        "district": district,
        "rooms": rooms,
        "median_price": stats.median_price,
        "avg_price": stats.avg_price,
        "median_price_per_sqm": stats.median_price_per_sqm,
        "avg_price_per_sqm": float(stats.avg_price_per_sqm),
        "active_count": stats.active_count,
        "sold_last_30d": velocity.sold_last_30d if velocity is not None else 0,
        "avg_days_on_market": velocity.avg_days_on_market if velocity is not None else None,
        "calculated_at": stats.calculated_at,
    }


def _deactivation_time(
    apartment: Apartment,
    inactive_changed_at: datetime | None,
) -> datetime | None:
    if inactive_changed_at is not None:
        return inactive_changed_at
    return apartment.last_seen_at


def _days_on_market(
    apartment: Apartment,
    inactive_changed_at: datetime | None,
) -> float | None:
    deactivation = _deactivation_time(apartment, inactive_changed_at)
    if apartment.first_seen_at is None or deactivation is None:
        return None
    return (deactivation - apartment.first_seen_at).total_seconds() / SECONDS_PER_DAY


def _compute_velocity_from_apartments(
    apartments: list[Apartment],
    inactive_changed_at_by_apartment: dict[int, datetime],
) -> SaleVelocity:
    cutoff = datetime.now(UTC) - timedelta(days=SOLD_WINDOW_DAYS)
    sold_last_30d = 0
    days_on_market: list[float] = []

    for apartment in apartments:
        inactive_changed_at = inactive_changed_at_by_apartment.get(apartment.id)
        deactivation = _deactivation_time(apartment, inactive_changed_at)
        if deactivation is not None and deactivation >= cutoff:
            sold_last_30d += 1

        days = _days_on_market(apartment, inactive_changed_at)
        if days is not None:
            days_on_market.append(days)

    avg_days_on_market = statistics.mean(days_on_market) if days_on_market else None
    median_days_on_market = (
        float(statistics.median(days_on_market)) if days_on_market else None
    )
    return SaleVelocity(
        sold_last_30d=sold_last_30d,
        avg_days_on_market=avg_days_on_market,
        median_days_on_market=median_days_on_market,
    )


class MarketAnalyticsService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def compute_complex_stats(
        self,
        complex_id: int,
        *,
        rooms: int | None = None,
    ) -> MarketStats | None:
        apartments = await apartment_repo.get_active_by_complex(
            self._session,
            complex_id,
            rooms=rooms,
            valid_external_id_only=True,
        )
        complex_name = await self._resolve_complex_name(complex_id)
        return _calculate_stats(
            apartments,
            complex_id=complex_id,
            complex_name=complex_name,
        )

    async def compute_district_stats(
        self,
        district: str,
        *,
        rooms: int | None = None,
    ) -> MarketStats | None:
        apartments = await apartment_repo.get_active_by_district(
            self._session,
            district,
            rooms=rooms,
        )
        return _calculate_stats(
            apartments,
            complex_id=0,
            complex_name=district,
        )

    async def compute_sale_velocity(
        self,
        complex_id: int | None = None,
        *,
        district: str | None = None,
        rooms: int | None = None,
    ) -> SaleVelocity:
        if complex_id is not None:
            apartments = await apartment_repo.get_inactive_by_complex(
                self._session,
                complex_id,
                rooms=rooms,
                valid_external_id_only=True,
            )
        elif district is not None:
            apartments = await apartment_repo.get_inactive_by_district(
                self._session,
                district,
                rooms=rooms,
            )
        else:
            msg = "compute_sale_velocity requires complex_id or district"
            raise ValueError(msg)

        inactive_changed_at = await self._get_latest_inactive_changed_at(
            [apartment.id for apartment in apartments],
        )
        return _compute_velocity_from_apartments(apartments, inactive_changed_at)

    async def compute_and_save_complex(
        self,
        complex_id: int,
        *,
        rooms: int | None = None,
    ) -> MarketAnalytics | None:
        apartments = await apartment_repo.get_active_by_complex(
            self._session,
            complex_id,
            rooms=rooms,
            valid_external_id_only=True,
        )
        complex_name = await self._resolve_complex_name(complex_id)
        stats = _calculate_stats(
            apartments,
            complex_id=complex_id,
            complex_name=complex_name,
        )
        if stats is None:
            return None

        district = await self._resolve_district(complex_id, apartments)
        velocity = await self.compute_sale_velocity(complex_id, rooms=rooms)
        return await analytics_repo.save_snapshot(
            self._session,
            _snapshot_from_stats(
                stats,
                complex_id=complex_id,
                district=district,
                rooms=rooms,
                velocity=velocity,
            ),
        )

    async def compute_and_save_all_complexes(self) -> int:
        complexes = await complex_repo.get_all(self._session)
        saved = 0
        for complex_ in complexes:
            if await self.compute_and_save_complex(complex_.id) is not None:
                saved += 1
        return saved

    async def compute_and_save_districts(self) -> int:
        districts = await apartment_repo.get_distinct_active_districts(self._session)
        saved = 0
        for district in districts:
            stats = await self.compute_district_stats(district)
            if stats is None:
                continue
            velocity = await self.compute_sale_velocity(district=district)
            await analytics_repo.save_snapshot(
                self._session,
                _snapshot_from_stats(
                    stats,
                    complex_id=None,
                    district=district,
                    rooms=None,
                    velocity=velocity,
                ),
            )
            saved += 1
        return saved

    async def _get_latest_inactive_changed_at(
        self,
        apartment_ids: list[int],
    ) -> dict[int, datetime]:
        if not apartment_ids:
            return {}
        result = await self._session.execute(
            select(
                ApartmentStatusHistory.apartment_id,
                func.max(ApartmentStatusHistory.changed_at),
            )
            .where(
                ApartmentStatusHistory.apartment_id.in_(apartment_ids),
                ApartmentStatusHistory.status == ApartmentStatus.INACTIVE,
            )
            .group_by(ApartmentStatusHistory.apartment_id),
        )
        return {apartment_id: changed_at for apartment_id, changed_at in result.all()}

    async def _resolve_complex_name(self, complex_id: int) -> str:
        result = await self._session.execute(
            select(ResidentialComplex).where(ResidentialComplex.id == complex_id),
        )
        complex_ = result.scalar_one_or_none()
        return complex_.name if complex_ is not None else str(complex_id)

    async def _resolve_district(
        self,
        complex_id: int,
        apartments: list[Apartment],
    ) -> str | None:
        result = await self._session.execute(
            select(ResidentialComplex).where(ResidentialComplex.id == complex_id),
        )
        complex_ = result.scalar_one_or_none()
        if complex_ is not None and complex_.district:
            return complex_.district
        if apartments:
            district = apartments[0].district
            return district or None
        return None
