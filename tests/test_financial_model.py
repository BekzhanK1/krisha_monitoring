from __future__ import annotations

from datetime import UTC, datetime

from app.analyzer.deal_analyzer import MarketStats
from app.analyzer.financial_model import calculate_deal_financials
from app.config import Settings
from app.models import Apartment


def _market_stats(*, median_price: int, median_price_per_sqm: int = 500_000) -> MarketStats:
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
    price: int,
    total_area: float = 60.0,
    condition: str | None = None,
    description: str | None = None,
) -> Apartment:
    return Apartment(
        external_id="test-1",
        url="https://krisha.kz/a/show/test-1",
        complex_id=1,
        price=price,
        price_per_sqm=price / total_area,
        rooms=2,
        total_area=total_area,
        condition=condition,
        description=description,
    )


def test_typical_two_room_deal_is_profitable() -> None:
    apartment = _apartment(price=25_000_000, total_area=31.0)
    market_stats = _market_stats(median_price=30_000_000)

    result = calculate_deal_financials(apartment, market_stats)

    assert result.purchase_price == 25_000_000
    assert result.expected_sale_price == 30_000_000
    assert result.profit > 0
    assert result.roi_pct > 0


def test_poor_condition_increases_renovation_cost() -> None:
    normal = calculate_deal_financials(
        _apartment(price=25_000_000, condition="хорошая"),
        _market_stats(median_price=30_000_000),
    )
    poor = calculate_deal_financials(
        _apartment(price=25_000_000, condition="требует ремонта"),
        _market_stats(median_price=30_000_000),
    )

    assert poor.renovation_cost == int(normal.renovation_cost * 1.5)


def test_expected_sale_price_falls_back_to_price_per_sqm() -> None:
    apartment = _apartment(price=25_000_000, total_area=60.0)
    market_stats = _market_stats(median_price=0, median_price_per_sqm=500_000)

    result = calculate_deal_financials(apartment, market_stats)

    assert result.expected_sale_price == 30_000_000


def test_no_capital_gains_tax_on_loss() -> None:
    apartment = _apartment(price=35_000_000)
    market_stats = _market_stats(median_price=30_000_000)

    result = calculate_deal_financials(apartment, market_stats)

    assert result.capital_gains_tax == 0
    assert result.profit < 0
    assert result.roi_pct < 0


def test_settings_investment_defaults() -> None:
    settings = Settings(database_url="postgresql+asyncpg://user:pass@host:5432/db")

    assert settings.renovation_per_sqm == 150_000
    assert settings.transaction_fee_pct == 0.01
    assert settings.capital_gains_tax_pct == 0.10
