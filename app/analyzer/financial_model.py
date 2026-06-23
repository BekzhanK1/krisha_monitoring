from __future__ import annotations

from dataclasses import dataclass

from app.analyzer.deal_analyzer import MarketStats
from app.models import Apartment

_POOR_CONDITION_KEYWORDS = ("требует ремонта", "без отделки")
_POOR_CONDITION_MULTIPLIER = 1.5


@dataclass
class DealFinancials:
    purchase_price: int
    renovation_cost: int
    transaction_costs: int
    expected_sale_price: int
    capital_gains_tax: int
    total_cost: int
    profit: int
    roi_pct: float


def calculate_deal_financials(
    apartment: Apartment,
    market_stats: MarketStats,
    *,
    renovation_per_sqm: int = 150_000,
    transaction_fee_pct: float = 0.01,
    capital_gains_tax_pct: float = 0.10,
) -> DealFinancials:
    purchase_price = apartment.price
    expected_sale_price = _expected_sale_price(apartment, market_stats)
    renovation_cost = _renovation_cost(apartment, renovation_per_sqm)
    transaction_costs = int(purchase_price * transaction_fee_pct)
    total_cost = purchase_price + renovation_cost + transaction_costs

    profit_before_tax = expected_sale_price - total_cost
    capital_gains_tax = (
        int(profit_before_tax * capital_gains_tax_pct) if profit_before_tax > 0 else 0
    )
    profit = expected_sale_price - total_cost - capital_gains_tax
    roi_pct = profit / total_cost * 100 if total_cost > 0 else 0.0

    return DealFinancials(
        purchase_price=purchase_price,
        renovation_cost=renovation_cost,
        transaction_costs=transaction_costs,
        expected_sale_price=expected_sale_price,
        capital_gains_tax=capital_gains_tax,
        total_cost=total_cost,
        profit=profit,
        roi_pct=roi_pct,
    )


def _expected_sale_price(apartment: Apartment, market_stats: MarketStats) -> int:
    if market_stats.median_price > 0:
        return market_stats.median_price
    return int(market_stats.median_price_per_sqm * apartment.total_area)


def _renovation_cost(apartment: Apartment, renovation_per_sqm: int) -> int:
    base = int(renovation_per_sqm * apartment.total_area)
    if _needs_extra_renovation(apartment):
        return int(base * _POOR_CONDITION_MULTIPLIER)
    return base


def _needs_extra_renovation(apartment: Apartment) -> bool:
    texts = [apartment.condition, apartment.description]
    for text in texts:
        if not text:
            continue
        lowered = text.lower()
        if any(keyword in lowered for keyword in _POOR_CONDITION_KEYWORDS):
            return True
    return False
