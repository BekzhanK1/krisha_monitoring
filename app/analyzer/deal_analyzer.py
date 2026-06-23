from __future__ import annotations

import statistics
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analyzer.seller_scorer import estimate_owner_probability
from app.config import get_settings
from app.models import Apartment, MarketAnalytics, ResidentialComplex
from app.models.seller import Seller, SellerType
from app.repositories import analytics_repo, apartment_repo, complex_repo, score_repo

if TYPE_CHECKING:
    from app.analyzer.investment_scorer import InvestmentGrade

MIN_ACTIVE_APARTMENTS = 5
CACHE_TTL = timedelta(minutes=5)
SNAPSHOT_MAX_AGE = timedelta(hours=24)
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
    grade: InvestmentGrade | None = None
    score: float | None = None
    roi_pct: float | None = None
    recommendation: str | None = None


GRADE_ORDER: tuple[str, ...] = ("A+", "A", "B", "C", "D")


def _grade_rank(grade: InvestmentGrade | None) -> int:
    if grade is None:
        return len(GRADE_ORDER)
    try:
        return GRADE_ORDER.index(grade.value)
    except ValueError:
        return len(GRADE_ORDER)


def _deal_sort_key(deal: Deal) -> tuple[int, float, float]:
    return (_grade_rank(deal.grade), -(deal.score or 0.0), -deal.discount_pct)


def _short_recommendation(reasons: list[str]) -> str:
    if not reasons:
        return "без явных сигналов"
    return "; ".join(reasons[:2])


def _parse_seller_type(value: str | None) -> SellerType | None:
    if value is None:
        return None
    try:
        return SellerType(value)
    except ValueError:
        return None


def clear_market_stats_cache() -> None:
    _stats_cache.clear()


def _market_stats_from_snapshot(snapshot: MarketAnalytics, complex_name: str) -> MarketStats:
    return MarketStats(
        complex_id=snapshot.complex_id or 0,
        complex_name=complex_name,
        median_price=snapshot.median_price,
        avg_price=snapshot.avg_price,
        median_price_per_sqm=snapshot.median_price_per_sqm,
        avg_price_per_sqm=int(snapshot.avg_price_per_sqm),
        active_count=snapshot.active_count,
        calculated_at=snapshot.calculated_at,
    )


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

        snapshot = await analytics_repo.get_latest_by_complex(self._session, complex_id)
        if snapshot is not None:
            calculated_at = snapshot.calculated_at
            if calculated_at.tzinfo is None:
                calculated_at = calculated_at.replace(tzinfo=UTC)
            if datetime.now(UTC) - calculated_at < SNAPSHOT_MAX_AGE:
                complex_name = await self._resolve_complex_name(complex_id)
                stats = _market_stats_from_snapshot(snapshot, complex_name)
                _stats_cache[complex_id] = (stats, datetime.now(UTC))
                return stats

        apartments = await apartment_repo.get_active_by_complex(self._session, complex_id)
        if len(apartments) < MIN_ACTIVE_APARTMENTS:
            return None

        complex_name = await self._resolve_complex_name(complex_id)

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

        try:
            from app.analyzer.market_analytics import MarketAnalyticsService

            await MarketAnalyticsService(self._session).compute_and_save_complex(complex_id)
        except Exception:
            pass

        return stats

    async def _resolve_complex_name(self, complex_id: int) -> str:
        result = await self._session.execute(
            select(ResidentialComplex).where(ResidentialComplex.id == complex_id),
        )
        complex_ = result.scalar_one_or_none()
        return complex_.name if complex_ is not None else str(complex_id)

    async def _resolve_owner_probability(self, apartment: Apartment) -> float:
        result = await self._session.execute(
            select(Seller).where(Seller.apartment_id == apartment.id).limit(1),
        )
        seller = result.scalar_one_or_none()
        if seller is not None and seller.owner_probability is not None:
            return seller.owner_probability

        seller_type = (
            seller.seller_type
            if seller is not None
            else _parse_seller_type(apartment.seller_type)
        )
        return estimate_owner_probability(
            seller_type=seller_type,
            description=apartment.description,
            seller_name=seller.name if seller is not None else None,
        )

    async def _resolve_scoring_fields(
        self,
        apartment: Apartment,
        deal: Deal,
        stats: MarketStats,
        *,
        top3_ids: set[int],
        top5_ids: set[int],
    ) -> tuple[InvestmentGrade | None, float | None, float | None, str | None]:
        from app.analyzer.financial_model import calculate_deal_financials
        from app.analyzer.investment_scorer import InvestmentGrade, InvestmentScorer

        stored = await score_repo.get_by_apartment_id(self._session, apartment.id)
        if stored is not None:
            return (
                InvestmentGrade(stored.grade),
                stored.score,
                stored.roi_pct,
                stored.recommendation,
            )

        owner_probability = await self._resolve_owner_probability(apartment)
        settings = get_settings()
        financials = calculate_deal_financials(
            apartment,
            stats,
            renovation_per_sqm=settings.renovation_per_sqm,
            transaction_fee_pct=settings.transaction_fee_pct,
            capital_gains_tax_pct=settings.capital_gains_tax_pct,
        )
        scored = InvestmentScorer().score(
            apartment,
            stats,
            deal=deal,
            owner_probability=owner_probability,
            is_top3_cheap=apartment.id in top3_ids,
            is_top5_cheap=apartment.id in top5_ids,
        )
        return (
            scored.grade,
            scored.score,
            financials.roi_pct,
            _short_recommendation(scored.reasons),
        )

    async def find_deals(self, complex_id: int) -> list[Deal]:
        stats = await self.get_market_stats(complex_id)
        if stats is None:
            return []

        apartments = await apartment_repo.get_active_by_complex(self._session, complex_id)
        sorted_by_price_per_sqm = sorted(apartments, key=lambda item: item.price_per_sqm)
        top3_ids = {apartment.id for apartment in sorted_by_price_per_sqm[:3]}
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

            deal = Deal(
                apartment=apartment,
                market_stats=stats,
                discount_pct=max(price_discount, pps_discount),
                deal_reasons=reasons,
                is_motivated_seller=bool(motivation_signs),
                motivation_signs=motivation_signs,
            )
            grade, score, roi_pct, recommendation = await self._resolve_scoring_fields(
                apartment,
                deal,
                stats,
                top3_ids=top3_ids,
                top5_ids=top5_ids,
            )
            deals.append(
                replace(
                    deal,
                    grade=grade,
                    score=score,
                    roi_pct=roi_pct,
                    recommendation=recommendation,
                ),
            )

        deals.sort(key=_deal_sort_key)
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

        all_deals.sort(key=_deal_sort_key)
        return all_deals
