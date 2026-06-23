from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.analyzer.deal_analyzer import Deal, MarketStats, detect_motivation_signs
from app.analyzer.types import SaleVelocity
from app.models import Apartment

# --- Grade thresholds (0–100 score) ---
GRADE_A_PLUS_MIN = 85.0
GRADE_A_MIN = 70.0
GRADE_B_MIN = 55.0
GRADE_C_MIN = 40.0

# --- Discount tiers (points) ---
DISCOUNT_POINTS_15_PCT = 45.0
DISCOUNT_POINTS_10_PCT = 40.0
DISCOUNT_POINTS_5_PCT = 22.0
DISCOUNT_POINTS_0_PCT = 10.0
DISCOUNT_PENALTY_ABOVE_MEDIAN = 5.0
DISCOUNT_PENALTY_WELL_ABOVE_MEDIAN = 12.0

# --- Other factor weights ---
MOTIVATION_POINTS = 30.0
OWNER_PROBABILITY_HIGH_MIN = 0.7
OWNER_PROBABILITY_HIGH_POINTS = 15.0
OWNER_PROBABILITY_MID_MIN = 0.5
OWNER_PROBABILITY_MID_POINTS = 8.0
TOP3_CHEAP_POINTS = 15.0
TOP5_CHEAP_POINTS = 8.0
FAST_SELLING_SOLD_30D_MIN = 5
FAST_SELLING_POINTS = 5.0
GOOD_FLOOR_POINTS = 3.0
RECENT_BUILD_POINTS = 3.0
RECENT_BUILD_YEAR_MIN = 2015


class InvestmentGrade(StrEnum):
    A_PLUS = "A+"
    A = "A"
    B = "B"
    C = "C"
    D = "D"


@dataclass
class ScoredApartment:
    apartment_id: int
    grade: InvestmentGrade
    score: float
    discount_pct: float
    reasons: list[str]


class InvestmentScorer:
    """Rule-based investment rating (no ML).

    Grade thresholds:
        >=85 → A+  (e.g. discount ≥15%, motivation, owner ≥0.7, TOP-3 price/m²)
        >=70 → A   (e.g. discount ≥10%, ≥2 deal signals)
        >=55 → B   (e.g. discount ≥5% or TOP-5)
        >=40 → C   (on market, no clear discount)
        <40  → D   (above median or weak complex)
    """

    def score(
        self,
        apartment: Apartment,
        market_stats: MarketStats,
        *,
        deal: Deal | None = None,
        owner_probability: float | None = None,
        sale_velocity: SaleVelocity | None = None,
        is_top5_cheap: bool = False,
        is_top3_cheap: bool = False,
    ) -> ScoredApartment:
        discount_pct = self._resolve_discount_pct(apartment, market_stats, deal)
        is_motivated, motivation_signs = self._resolve_motivation(apartment, deal)

        score = 0.0
        reasons: list[str] = []

        discount_points = _discount_points(discount_pct)
        score += discount_points
        if discount_pct >= 15:
            reasons.append(f"дисконт {discount_pct:.1f}% (≥15%)")
        elif discount_pct >= 10:
            reasons.append(f"дисконт {discount_pct:.1f}% (≥10%)")
        elif discount_pct >= 5:
            reasons.append(f"дисконт {discount_pct:.1f}%")
        elif discount_pct < 0:
            reasons.append(f"цена выше медианы на {abs(discount_pct):.1f}%")

        if is_motivated:
            score += MOTIVATION_POINTS
            signs = ", ".join(motivation_signs)
            reasons.append(f"мотивация продавца ({signs})")

        if owner_probability is not None:
            if owner_probability >= OWNER_PROBABILITY_HIGH_MIN:
                score += OWNER_PROBABILITY_HIGH_POINTS
                reasons.append(f"высокая вероятность собственника ({owner_probability:.0%})")
            elif owner_probability >= OWNER_PROBABILITY_MID_MIN:
                score += OWNER_PROBABILITY_MID_POINTS
                reasons.append(f"вероятность собственника {owner_probability:.0%}")

        if is_top3_cheap:
            score += TOP3_CHEAP_POINTS
            reasons.append("ТОП-3 дешёвых по цене/м²")
        elif is_top5_cheap:
            score += TOP5_CHEAP_POINTS
            reasons.append("ТОП-5 дешёвых по цене/м²")

        if sale_velocity is not None and sale_velocity.sold_last_30d >= FAST_SELLING_SOLD_30D_MIN:
            score += FAST_SELLING_POINTS
            reasons.append(f"активные продажи в ЖК ({sale_velocity.sold_last_30d} за 30 дн.)")

        floor_bonus = _floor_bonus(apartment)
        if floor_bonus > 0:
            score += floor_bonus
            reasons.append("удобный этаж")

        year_bonus = _year_built_bonus(apartment)
        if year_bonus > 0:
            score += year_bonus
            reasons.append(f"новый дом ({apartment.year_built} г.)")

        score = max(0.0, min(100.0, score))
        grade = _grade_from_score(score)

        if not reasons:
            reasons.append("без явных инвестиционных сигналов")

        return ScoredApartment(
            apartment_id=apartment.id,
            grade=grade,
            score=score,
            discount_pct=discount_pct,
            reasons=reasons,
        )

    def _resolve_discount_pct(
        self,
        apartment: Apartment,
        market_stats: MarketStats,
        deal: Deal | None,
    ) -> float:
        if deal is not None:
            return deal.discount_pct
        return _compute_discount_pct(apartment, market_stats)

    def _resolve_motivation(
        self,
        apartment: Apartment,
        deal: Deal | None,
    ) -> tuple[bool, list[str]]:
        if deal is not None:
            return deal.is_motivated_seller, list(deal.motivation_signs)
        signs = detect_motivation_signs(apartment.description)
        return bool(signs), signs


def _compute_discount_pct(apartment: Apartment, market_stats: MarketStats) -> float:
    if market_stats.median_price <= 0 or market_stats.median_price_per_sqm <= 0:
        return 0.0
    price_discount = (
        (market_stats.median_price - apartment.price) / market_stats.median_price * 100
    )
    pps_discount = (
        (market_stats.median_price_per_sqm - apartment.price_per_sqm)
        / market_stats.median_price_per_sqm
        * 100
    )
    return max(price_discount, pps_discount)


def _discount_points(discount_pct: float) -> float:
    if discount_pct >= 15:
        return DISCOUNT_POINTS_15_PCT
    if discount_pct >= 10:
        return DISCOUNT_POINTS_10_PCT
    if discount_pct >= 5:
        return DISCOUNT_POINTS_5_PCT
    if discount_pct >= 0:
        return DISCOUNT_POINTS_0_PCT
    if discount_pct >= -5:
        return -DISCOUNT_PENALTY_ABOVE_MEDIAN
    return -DISCOUNT_PENALTY_WELL_ABOVE_MEDIAN


def _floor_bonus(apartment: Apartment) -> float:
    if apartment.floor is None or apartment.total_floors is None:
        return 0.0
    if apartment.floor <= 1 or apartment.floor >= apartment.total_floors:
        return 0.0
    return GOOD_FLOOR_POINTS


def _year_built_bonus(apartment: Apartment) -> float:
    if apartment.year_built is None:
        return 0.0
    if apartment.year_built >= RECENT_BUILD_YEAR_MIN:
        return RECENT_BUILD_POINTS
    return 0.0


def _grade_from_score(score: float) -> InvestmentGrade:
    if score >= GRADE_A_PLUS_MIN:
        return InvestmentGrade.A_PLUS
    if score >= GRADE_A_MIN:
        return InvestmentGrade.A
    if score >= GRADE_B_MIN:
        return InvestmentGrade.B
    if score >= GRADE_C_MIN:
        return InvestmentGrade.C
    return InvestmentGrade.D
