from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.analyzer.deal_analyzer import (
    DealAnalyzer,
    clear_market_stats_cache,
    detect_motivation_signs,
)
from app.repositories import apartment_repo, complex_repo


def _apartment_data(
    complex_id: int,
    external_id: str,
    *,
    price: int,
    price_per_sqm: float,
    description: str | None = None,
) -> dict:
    return {
        "external_id": external_id,
        "url": f"https://krisha.kz/a/show/{external_id}",
        "complex_id": complex_id,
        "price": price,
        "price_per_sqm": price_per_sqm,
        "district": "Esil",
        "address": "Test Street",
        "rooms": 2,
        "total_area": 100.0,
        "floor": 5,
        "total_floors": 16,
        "description": description,
    }


@pytest.fixture(autouse=True)
def clear_cache() -> None:
    clear_market_stats_cache()
    yield
    clear_market_stats_cache()


@pytest.mark.asyncio
async def test_get_market_stats_requires_minimum_apartments(db_session: AsyncSession) -> None:
    suffix = uuid.uuid4().hex[:8]
    complex_ = await complex_repo.get_or_create(db_session, f"Stats Complex {suffix}")
    analyzer = DealAnalyzer(db_session)

    for index in range(4):
        await apartment_repo.upsert_apartment(
            db_session,
            _apartment_data(
                complex_.id,
                f"stats-{suffix}-{index}",
                price=50_000_000 + index,
                price_per_sqm=500_000 + index,
            ),
        )

    assert await analyzer.get_market_stats(complex_.id) is None


@pytest.mark.asyncio
async def test_get_market_stats_calculates_medians(db_session: AsyncSession) -> None:
    suffix = uuid.uuid4().hex[:8]
    complex_ = await complex_repo.get_or_create(db_session, f"Median Complex {suffix}")
    analyzer = DealAnalyzer(db_session)
    prices = [40_000_000, 50_000_000, 60_000_000, 70_000_000, 80_000_000]

    for index, price in enumerate(prices):
        await apartment_repo.upsert_apartment(
            db_session,
            _apartment_data(
                complex_.id,
                f"median-{suffix}-{index}",
                price=price,
                price_per_sqm=price / 100,
            ),
        )

    stats = await analyzer.get_market_stats(complex_.id)
    assert stats is not None
    assert stats.median_price == 60_000_000
    assert stats.avg_price == 60_000_000
    assert stats.active_count == 5
    assert stats.complex_name == complex_.name


@pytest.mark.asyncio
async def test_find_deals_detects_discount_and_motivation(db_session: AsyncSession) -> None:
    suffix = uuid.uuid4().hex[:8]
    complex_ = await complex_repo.get_or_create(db_session, f"Deal Complex {suffix}")
    analyzer = DealAnalyzer(db_session)
    base_prices = [100_000_000, 100_000_000, 100_000_000, 100_000_000]

    for index, price in enumerate(base_prices):
        await apartment_repo.upsert_apartment(
            db_session,
            _apartment_data(
                complex_.id,
                f"base-{suffix}-{index}",
                price=price,
                price_per_sqm=1_000_000,
            ),
        )

    cheap, _, _ = await apartment_repo.upsert_apartment(
        db_session,
        _apartment_data(
            complex_.id,
            f"cheap-{suffix}",
            price=70_000_000,
            price_per_sqm=700_000,
            description="Срочно продам, возможен торг",
        ),
    )

    deals = await analyzer.find_deals(complex_.id)
    assert len(deals) >= 1
    top_deal = deals[0]
    assert top_deal.apartment.id == cheap.id
    assert top_deal.discount_pct > 10
    assert top_deal.is_motivated_seller is True
    assert "срочно" in top_deal.motivation_signs
    assert "торг" in top_deal.motivation_signs


@pytest.mark.asyncio
async def test_analyze_all_complexes_sorted_by_discount(db_session: AsyncSession) -> None:
    suffix = uuid.uuid4().hex[:8]
    complex_a = await complex_repo.get_or_create(db_session, f"Complex A {suffix}")
    complex_b = await complex_repo.get_or_create(db_session, f"Complex B {suffix}")
    analyzer = DealAnalyzer(db_session)

    for complex_, base_price, cheap_price, label in (
        (complex_a, 100_000_000, 80_000_000, "a"),
        (complex_b, 100_000_000, 60_000_000, "b"),
    ):
        for index in range(4):
            await apartment_repo.upsert_apartment(
                db_session,
                _apartment_data(
                    complex_.id,
                    f"{label}-base-{suffix}-{index}",
                    price=base_price,
                    price_per_sqm=base_price / 100,
                ),
            )
        await apartment_repo.upsert_apartment(
            db_session,
            _apartment_data(
                complex_.id,
                f"{label}-cheap-{suffix}",
                price=cheap_price,
                price_per_sqm=cheap_price / 100,
            ),
        )

    deals = await analyzer.analyze_all_complexes()
    assert len(deals) >= 2
    assert deals[0].discount_pct >= deals[1].discount_pct


def test_detect_motivation_signs() -> None:
    signs = detect_motivation_signs("Срочно продам, нужен переезд, ипотека одобрена")
    assert signs == ["срочно", "переезд", "ипотека"]
