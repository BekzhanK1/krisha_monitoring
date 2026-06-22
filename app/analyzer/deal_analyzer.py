from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Apartment, ResidentialComplex
from app.repositories import apartment_repo, complex_repo

MIN_ACTIVE_APARTMENTS = 5
CACHE_TTL = timedelta(minutes=30)
MOTIVATION_KEYWORDS = ("срочно", "торг", "переезд", "ипотека", "снижение")

_stats_cache: dict[int, tuple[MarketStats, datetime]] = {}


@dataclass
class MarketStats:
    complex_id: int
    complex_name: str
    median_price: int
    avg_price: int
    median_price_per_sqm: int
    avg_price_per_sqm: int
    active_count: int
    calculated_at: datetime


@dataclass
class Deal:
    apartment: Apartment
    market_stats: MarketStats
    discount_pct: float
    deal_reasons: list[str]
    is_motivated_seller: bool
    motivation_signs: list[str]


def clear_market_stats_cache() -> None:
    _stats_cache.clear()


def detect_motivation_signs(description: str | None) -> list[str]:
    if not description:
        return []
    lowered = description.lower()
    return [word for word in MOTIVATION_KEYWORDS if word in lowered]


class DealAnalyzer:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_market_stats(self, complex_id: int) -> MarketStats | None:
        cached = _stats_cache.get(complex_id)
        if cached is not None:
            stats, cached_at = cached
            if datetime.now(UTC) - cached_at < CACHE_TTL:
                return stats

        apartments = await apartment_repo.get_active_by_complex(self._session, complex_id)
        if len(apartments) < MIN_ACTIVE_APARTMENTS:
            return None

        result = await self._session.execute(
            select(ResidentialComplex).where(ResidentialComplex.id == complex_id),
        )
        complex_ = result.scalar_one_or_none()
        complex_name = complex_.name if complex_ is not None else str(complex_id)

        prices = [apartment.price for apartment in apartments]
        prices_per_sqm = [apartment.price_per_sqm for apartment in apartments]

        stats = MarketStats(
            complex_id=complex_id,
            complex_name=complex_name,
            median_price=int(statistics.median(prices)),
            avg_price=int(statistics.mean(prices)),
            median_price_per_sqm=int(statistics.median(prices_per_sqm)),
            avg_price_per_sqm=int(statistics.mean(prices_per_sqm)),
            active_count=len(apartments),
            calculated_at=datetime.now(UTC),
        )
        _stats_cache[complex_id] = (stats, datetime.now(UTC))
        return stats

    async def find_deals(self, complex_id: int) -> list[Deal]:
        stats = await self.get_market_stats(complex_id)
        if stats is None:
            return []

        apartments = await apartment_repo.get_active_by_complex(self._session, complex_id)
        sorted_by_price_per_sqm = sorted(apartments, key=lambda item: item.price_per_sqm)
        top5_ids = {apartment.id for apartment in sorted_by_price_per_sqm[:5]}

        deals: list[Deal] = []
        for apartment in apartments:
            reasons: list[str] = []
            if apartment.price < stats.median_price * 0.9:
                reasons.append("цена ниже медианы")
            if apartment.price_per_sqm < stats.median_price_per_sqm * 0.9:
                reasons.append("цена/м² ниже медианы")
            if apartment.id in top5_ids:
                reasons.append("ТОП-5 дешёвых")

            if not reasons:
                continue

            price_discount = (stats.median_price - apartment.price) / stats.median_price * 100
            pps_discount = (
                (stats.median_price_per_sqm - apartment.price_per_sqm)
                / stats.median_price_per_sqm
                * 100
            )
            motivation_signs = detect_motivation_signs(apartment.description)

            deals.append(
                Deal(
                    apartment=apartment,
                    market_stats=stats,
                    discount_pct=max(price_discount, pps_discount),
                    deal_reasons=reasons,
                    is_motivated_seller=bool(motivation_signs),
                    motivation_signs=motivation_signs,
                ),
            )

        deals.sort(key=lambda deal: deal.discount_pct, reverse=True)
        return deals

    async def analyze_all_complexes(self) -> list[Deal]:
        complexes = await complex_repo.get_all(self._session)
        all_deals: list[Deal] = []
        seen_apartment_ids: set[int] = set()

        for complex_ in complexes:
            for deal in await self.find_deals(complex_.id):
                if deal.apartment.id in seen_apartment_ids:
                    continue
                seen_apartment_ids.add(deal.apartment.id)
                all_deals.append(deal)

        all_deals.sort(key=lambda deal: deal.discount_pct, reverse=True)
        return all_deals
