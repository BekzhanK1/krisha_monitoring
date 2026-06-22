from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analyzer.deal_analyzer import Deal, MarketStats
from app.models import Apartment, Notification
from app.repositories import apartment_repo, complex_repo
from app.telegram.notifications import notify_new_deals


def _make_deal(apartment: Apartment, complex_name: str) -> Deal:
    stats = MarketStats(
        complex_id=apartment.complex_id,
        complex_name=complex_name,
        median_price=100_000_000,
        avg_price=100_000_000,
        median_price_per_sqm=1_000_000,
        avg_price_per_sqm=1_000_000,
        active_count=5,
        calculated_at=datetime.now(UTC),
    )
    return Deal(
        apartment=apartment,
        market_stats=stats,
        discount_pct=20.0,
        deal_reasons=["цена ниже медианы"],
        is_motivated_seller=False,
        motivation_signs=[],
    )


@pytest.mark.asyncio
async def test_notify_new_deals_sends_and_records(db_session: AsyncSession) -> None:
    suffix = uuid.uuid4().hex[:8]
    complex_ = await complex_repo.get_or_create(db_session, f"Notify Complex {suffix}")
    apartment, _, _ = await apartment_repo.upsert_apartment(
        db_session,
        {
            "external_id": f"notify-{suffix}",
            "url": f"https://krisha.kz/a/show/notify-{suffix}",
            "complex_id": complex_.id,
            "price": 80_000_000,
            "price_per_sqm": 800_000,
            "district": "Esil",
            "address": "Street",
            "rooms": 2,
            "total_area": 100.0,
        },
    )
    await db_session.commit()

    sender = AsyncMock(return_value=True)
    deal = _make_deal(apartment, complex_.name)
    sent = await notify_new_deals([deal], db_session, sender_fn=sender)

    assert sent == 1
    sender.assert_awaited_once()

    result = await db_session.execute(
        select(Notification).where(Notification.apartment_id == apartment.id),
    )
    notification = result.scalar_one()
    assert notification.notification_type == "deal_alert"
    assert notification.is_sent is True


@pytest.mark.asyncio
async def test_notify_new_deals_skips_recent_duplicate(db_session: AsyncSession) -> None:
    suffix = uuid.uuid4().hex[:8]
    complex_ = await complex_repo.get_or_create(db_session, f"Dedup Complex {suffix}")
    apartment, _, _ = await apartment_repo.upsert_apartment(
        db_session,
        {
            "external_id": f"dedup-{suffix}",
            "url": f"https://krisha.kz/a/show/dedup-{suffix}",
            "complex_id": complex_.id,
            "price": 80_000_000,
            "price_per_sqm": 800_000,
            "district": "Esil",
            "address": "Street",
            "rooms": 2,
            "total_area": 100.0,
        },
    )
    db_session.add(
        Notification(
            apartment_id=apartment.id,
            notification_type="deal_alert",
            message="previous",
            sent_at=datetime.now(UTC) - timedelta(hours=1),
            is_sent=True,
        ),
    )
    await db_session.commit()

    sender = AsyncMock(return_value=True)
    deal = _make_deal(apartment, complex_.name)
    sent = await notify_new_deals([deal], db_session, sender_fn=sender)

    assert sent == 0
    sender.assert_not_awaited()


@pytest.mark.asyncio
async def test_notify_new_deals_records_failed_send(db_session: AsyncSession) -> None:
    suffix = uuid.uuid4().hex[:8]
    complex_ = await complex_repo.get_or_create(db_session, f"Fail Complex {suffix}")
    apartment, _, _ = await apartment_repo.upsert_apartment(
        db_session,
        {
            "external_id": f"fail-{suffix}",
            "url": f"https://krisha.kz/a/show/fail-{suffix}",
            "complex_id": complex_.id,
            "price": 80_000_000,
            "price_per_sqm": 800_000,
            "district": "Esil",
            "address": "Street",
            "rooms": 2,
            "total_area": 100.0,
        },
    )
    await db_session.commit()

    sender = AsyncMock(return_value=False)
    deal = _make_deal(apartment, complex_.name)
    sent = await notify_new_deals([deal], db_session, sender_fn=sender)

    assert sent == 0
    result = await db_session.execute(
        select(Notification).where(Notification.apartment_id == apartment.id),
    )
    notification = result.scalar_one()
    assert notification.is_sent is False
