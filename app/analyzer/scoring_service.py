from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analyzer.deal_analyzer import Deal, DealAnalyzer, MarketStats, detect_motivation_signs
from app.analyzer.financial_model import calculate_deal_financials
from app.analyzer.investment_scorer import InvestmentScorer
from app.analyzer.market_analytics import MarketAnalyticsService
from app.analyzer.seller_scorer import estimate_owner_probability
from app.analyzer.types import SaleVelocity
from app.config import get_settings
from app.models import Apartment
from app.models.apartment_score import ApartmentScore
from app.models.seller import Seller, SellerType
from app.repositories import apartment_repo, score_repo


def _parse_seller_type(value: str | None) -> SellerType | None:
    if value is None:
        return None
    try:
        return SellerType(value)
    except ValueError:
        return None


def _build_deal(
    apartment: Apartment,
    market_stats: MarketStats,
    *,
    top5_ids: set[int],
) -> Deal | None:
    reasons: list[str] = []
    if apartment.price < market_stats.median_price * 0.9:
        reasons.append("цена ниже медианы")
    if apartment.price_per_sqm < market_stats.median_price_per_sqm * 0.9:
        reasons.append("цена/м² ниже медианы")
    if apartment.id in top5_ids:
        reasons.append("ТОП-5 дешёвых")

    price_discount = (market_stats.median_price - apartment.price) / market_stats.median_price * 100
    pps_discount = (
        (market_stats.median_price_per_sqm - apartment.price_per_sqm)
        / market_stats.median_price_per_sqm
        * 100
    )
    motivation_signs = detect_motivation_signs(apartment.description)

    return Deal(
        apartment=apartment,
        market_stats=market_stats,
        discount_pct=max(price_discount, pps_discount),
        deal_reasons=reasons,
        is_motivated_seller=bool(motivation_signs),
        motivation_signs=motivation_signs,
    )


def _top_cheap_ids(apartments: list[Apartment], *, top_n: int) -> set[int]:
    sorted_by_price_per_sqm = sorted(apartments, key=lambda item: item.price_per_sqm)
    return {apartment.id for apartment in sorted_by_price_per_sqm[:top_n]}


def _build_recommendation(scored_reasons: list[str], grade: str, roi_pct: float) -> str:
    highlights = "; ".join(scored_reasons[:2]) if scored_reasons else "без явных сигналов"
    return f"Рейтинг {grade}: {highlights}. Ожидаемый ROI {roi_pct:.1f}%."


async def _resolve_owner_probability(session: AsyncSession, apartment: Apartment) -> float:
    result = await session.execute(
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


async def _resolve_sale_velocity(
    session: AsyncSession,
    complex_id: int,
    cache: dict[int, SaleVelocity],
) -> SaleVelocity | None:
    if complex_id in cache:
        return cache[complex_id]
    try:
        velocity = await MarketAnalyticsService(session).compute_sale_velocity(complex_id)
    except Exception:
        return None
    cache[complex_id] = velocity
    return velocity


async def score_apartment(
    session: AsyncSession,
    apartment: Apartment,
    *,
    market_stats: MarketStats | None = None,
    top3_ids: set[int] | None = None,
    top5_ids: set[int] | None = None,
    sale_velocity: SaleVelocity | None = None,
) -> ApartmentScore | None:
    analyzer = DealAnalyzer(session)
    stats = market_stats or await analyzer.get_market_stats(apartment.complex_id)
    if stats is None:
        return None

    if top3_ids is None or top5_ids is None:
        complex_apartments = await apartment_repo.get_active_by_complex(
            session,
            apartment.complex_id,
            valid_external_id_only=True,
        )
        top3_ids = top3_ids or _top_cheap_ids(complex_apartments, top_n=3)
        top5_ids = top5_ids or _top_cheap_ids(complex_apartments, top_n=5)

    deal = _build_deal(apartment, stats, top5_ids=top5_ids)
    owner_probability = await _resolve_owner_probability(session, apartment)
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
        sale_velocity=sale_velocity,
        is_top3_cheap=apartment.id in top3_ids,
        is_top5_cheap=apartment.id in top5_ids,
    )
    recommendation = _build_recommendation(
        scored.reasons,
        scored.grade.value,
        financials.roi_pct,
    )
    return await score_repo.upsert_score(
        session,
        apartment.id,
        {
            "grade": scored.grade.value,
            "score": scored.score,
            "discount_pct": scored.discount_pct,
            "roi_pct": financials.roi_pct,
            "owner_probability": owner_probability,
            "recommendation": recommendation,
            "calculated_at": datetime.now(UTC),
        },
    )


async def score_all_active(session: AsyncSession) -> int:
    apartments = await apartment_repo.get_all_active(session, valid_external_id_only=True)
    if not apartments:
        return 0

    analyzer = DealAnalyzer(session)
    by_complex: dict[int, list[Apartment]] = {}
    for apartment in apartments:
        by_complex.setdefault(apartment.complex_id, []).append(apartment)

    complex_stats: dict[int, MarketStats] = {}
    complex_top3: dict[int, set[int]] = {}
    complex_top5: dict[int, set[int]] = {}
    velocity_cache: dict[int, SaleVelocity] = {}

    for complex_id, complex_apartments in by_complex.items():
        stats = await analyzer.get_market_stats(complex_id)
        if stats is None:
            continue
        complex_stats[complex_id] = stats
        complex_top3[complex_id] = _top_cheap_ids(complex_apartments, top_n=3)
        complex_top5[complex_id] = _top_cheap_ids(complex_apartments, top_n=5)

    scored_count = 0
    for apartment in apartments:
        stats = complex_stats.get(apartment.complex_id)
        if stats is None:
            continue
        velocity = await _resolve_sale_velocity(session, apartment.complex_id, velocity_cache)
        result = await score_apartment(
            session,
            apartment,
            market_stats=stats,
            top3_ids=complex_top3[apartment.complex_id],
            top5_ids=complex_top5[apartment.complex_id],
            sale_velocity=velocity,
        )
        if result is not None:
            scored_count += 1

    return scored_count
