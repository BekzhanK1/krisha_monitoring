from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.analyzer.deal_analyzer import Deal, MarketStats
from app.analyzer.investment_scorer import (
    GRADE_A_MIN,
    InvestmentGrade,
    InvestmentScorer,
)
from app.analyzer.types import SaleVelocity
from app.models import Apartment


def _market_stats(
    *,
    median_price: int = 50_000_000,
    median_price_per_sqm: int = 500_000,
) -> MarketStats:
    return MarketStats(
        complex_id=1,
        complex_name="Test Complex",
        median_price=median_price,
        avg_price=median_price,
        median_price_per_sqm=median_price_per_sqm,
        avg_price_per_sqm=median_price_per_sqm,
        active_count=10,
        calculated_at=datetime.now(UTC),
    )


def _apartment(
    *,
    apartment_id: int = 1,
    price: int = 44_000_000,
    price_per_sqm: float = 440_000,
    description: str | None = None,
    floor: int | None = 5,
    total_floors: int | None = 16,
    year_built: int | None = 2018,
) -> Apartment:
    return Apartment(
        id=apartment_id,
        external_id=f"ext-{apartment_id}",
        url=f"https://krisha.kz/a/show/ext-{apartment_id}",
        complex_id=1,
        price=price,
        price_per_sqm=price_per_sqm,
        district="Esil",
        address="Test Street",
        rooms=2,
        total_area=100.0,
        floor=floor,
        total_floors=total_floors,
        year_built=year_built,
        description=description,
    )


def test_twelve_percent_discount_with_urgent_description_scores_at_least_a() -> None:
    apartment = _apartment(description="Срочно продам, возможен торг")
    stats = _market_stats()
    scorer = InvestmentScorer()

    result = scorer.score(apartment, stats)

    assert result.discount_pct == pytest.approx(12.0)
    assert result.score >= GRADE_A_MIN
    assert result.grade in {InvestmentGrade.A, InvestmentGrade.A_PLUS}
    assert any("мотивация" in reason for reason in result.reasons)


def test_a_plus_grade_when_all_strong_signals_present() -> None:
    apartment = _apartment(
        price=40_000_000,
        price_per_sqm=400_000,
        description="Срочно, торг",
    )
    stats = _market_stats()
    scorer = InvestmentScorer()

    result = scorer.score(
        apartment,
        stats,
        owner_probability=0.75,
        is_top3_cheap=True,
    )

    assert result.discount_pct >= 15
    assert result.grade == InvestmentGrade.A_PLUS
    assert result.score >= 85
    assert any("дисконт" in reason for reason in result.reasons)
    assert any("собственник" in reason for reason in result.reasons)
    assert any("ТОП-3" in reason for reason in result.reasons)


def test_uses_deal_discount_and_motivation_when_provided() -> None:
    apartment = _apartment(price=55_000_000, price_per_sqm=550_000)
    stats = _market_stats()
    deal = Deal(
        apartment=apartment,
        market_stats=stats,
        discount_pct=18.0,
        deal_reasons=["цена ниже медианы"],
        is_motivated_seller=True,
        motivation_signs=["срочно"],
    )
    scorer = InvestmentScorer()

    result = scorer.score(apartment, stats, deal=deal)

    assert result.discount_pct == pytest.approx(18.0)
    assert result.grade == InvestmentGrade.A
    assert result.score >= GRADE_A_MIN


def test_above_median_price_gets_low_grade() -> None:
    apartment = _apartment(price=60_000_000, price_per_sqm=600_000, description=None)
    stats = _market_stats()
    scorer = InvestmentScorer()

    result = scorer.score(apartment, stats)

    assert result.discount_pct < 0
    assert result.grade == InvestmentGrade.D
    assert result.score < 40


def test_fast_selling_complex_adds_small_bonus() -> None:
    apartment = _apartment(
        price=47_500_000,
        price_per_sqm=475_000,
        description=None,
    )
    stats = _market_stats()
    scorer = InvestmentScorer()
    velocity = SaleVelocity(
        sold_last_30d=8,
        avg_days_on_market=30.0,
        median_days_on_market=25.0,
    )

    without_velocity = scorer.score(apartment, stats)
    with_velocity = scorer.score(apartment, stats, sale_velocity=velocity)

    assert with_velocity.score == pytest.approx(without_velocity.score + 5.0)
    assert any("продажи" in reason for reason in with_velocity.reasons)
