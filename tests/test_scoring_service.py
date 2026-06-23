from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.analyzer.scoring_service import score_all_active, score_apartment
from app.models.seller import Seller, SellerType
from app.repositories import apartment_repo, complex_repo, score_repo


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


@pytest.mark.asyncio
async def test_score_apartment_persists_score(db_session: AsyncSession) -> None:
    suffix = uuid.uuid4().hex[:8]
    complex_ = await complex_repo.get_or_create(db_session, f"Score Complex {suffix}")
    prices = [40_000_000, 50_000_000, 60_000_000, 70_000_000, 80_000_000]
    base_id = 70_000_000 + int(suffix[:6], 16) % 1_000_000
    target = None
    for index, price in enumerate(prices):
        apartment, _, _ = await apartment_repo.upsert_apartment(
            db_session,
            _apartment_data(
                complex_.id,
                str(base_id + index),
                price=price,
                price_per_sqm=price / 100,
                description="срочно продам" if index == 0 else None,
            ),
        )
        if index == 0:
            target = apartment
    assert target is not None
    await db_session.flush()

    result = await score_apartment(db_session, target)
    assert result is not None
    assert result.apartment_id == target.id
    assert result.grade in {"A+", "A", "B", "C", "D"}
    assert result.score > 0
    assert result.discount_pct > 0
    assert result.owner_probability is not None
    assert "ROI" in result.recommendation

    stored = await score_repo.get_by_apartment_id(db_session, target.id)
    assert stored is not None
    assert stored.grade == result.grade


@pytest.mark.asyncio
async def test_score_apartment_uses_seller_owner_probability(db_session: AsyncSession) -> None:
    suffix = uuid.uuid4().hex[:8]
    complex_ = await complex_repo.get_or_create(db_session, f"Seller Score Complex {suffix}")
    prices = [40_000_000, 50_000_000, 60_000_000, 70_000_000, 80_000_000]
    base_id = 80_000_000 + int(suffix[:6], 16) % 1_000_000
    target = None
    for index, price in enumerate(prices):
        apartment, _, _ = await apartment_repo.upsert_apartment(
            db_session,
            _apartment_data(
                complex_.id,
                str(base_id + index),
                price=price,
                price_per_sqm=price / 100,
            ),
        )
        if index == 0:
            target = apartment
    assert target is not None
    db_session.add(
        Seller(
            apartment_id=target.id,
            seller_type=SellerType.OWNER,
            owner_probability=0.92,
            name="Owner",
        ),
    )
    await db_session.flush()

    result = await score_apartment(db_session, target)
    assert result is not None
    assert result.owner_probability == 0.92


@pytest.mark.asyncio
async def test_score_all_active_counts_scored_apartments(db_session: AsyncSession) -> None:
    suffix = uuid.uuid4().hex[:8]
    complex_ = await complex_repo.get_or_create(db_session, f"Bulk Score Complex {suffix}")
    prices = [40_000_000, 50_000_000, 60_000_000, 70_000_000, 80_000_000]
    base_id = 90_000_000 + int(suffix[:6], 16) % 1_000_000
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
    await db_session.flush()

    scored_count = await score_all_active(db_session)
    assert scored_count == 5


@pytest.mark.asyncio
async def test_score_apartment_returns_none_without_market_stats(
    db_session: AsyncSession,
) -> None:
    suffix = uuid.uuid4().hex[:8]
    complex_ = await complex_repo.get_or_create(db_session, f"Tiny Complex {suffix}")
    apartment, _, _ = await apartment_repo.upsert_apartment(
        db_session,
        _apartment_data(
            complex_.id,
            str(100_000_000 + int(suffix[:6], 16) % 1_000_000),
            price=50_000_000,
            price_per_sqm=500_000,
        ),
    )
    await db_session.flush()

    result = await score_apartment(db_session, apartment)
    assert result is None
