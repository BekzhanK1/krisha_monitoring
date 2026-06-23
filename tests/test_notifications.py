from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analyzer.deal_analyzer import Deal, MarketStats
from app.analyzer.investment_scorer import InvestmentGrade
from app.models import Apartment, Notification
from app.repositories import apartment_repo, complex_repo
from app.telegram.notifications import (
    NOTIFICATION_TYPE_NEW_DEAL,
    format_deal_alert,
    format_deal_message,
    format_hunter_alert,
    notify_new_deals,
)


def _make_deal(
    apartment: Apartment,
    complex_name: str,
    *,
    grade: InvestmentGrade | None = None,
    roi_pct: float | None = None,
    recommendation: str | None = None,
) -> Deal:
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
        grade=grade,
        roi_pct=roi_pct,
        recommendation=recommendation,
    )


def test_format_deal_alert_tz_format() -> None:
    apartment = Apartment(
        external_id="123456",
        url="https://krisha.kz/a/show/123456",
        complex_id=1,
        price=24_500_000,
        price_per_sqm=470_000,
        district="Esil",
        address="Street",
        rooms=2,
        total_area=52.0,
    )
    deal = _make_deal(
        apartment,
        "EXPO Residence",
        grade=InvestmentGrade.A,
        roi_pct=11.0,
        recommendation="Срочная продажа ниже медианы ЖК, высокая вероятность собственника.",
    )
    deal.discount_pct = 14.0

    message = format_deal_alert(deal)

    assert "ЖК: EXPO Residence" in message
    assert "24.5 млн (-14%)" in message
    assert "Площадь: 52 м²" in message
    assert "Рейтинг: A" in message
    assert "ROI: ~11%" in message
    assert "Ссылка:" in message
    assert "Срочная продажа ниже медианы ЖК" in message


def test_format_hunter_alert_includes_urgency_header() -> None:
    apartment = Apartment(
        external_id="123456",
        url="https://krisha.kz/a/show/123456",
        complex_id=1,
        price=80_000_000,
        price_per_sqm=800_000,
        district="Esil",
        address="Street",
        rooms=2,
        total_area=100.0,
    )
    deal = _make_deal(apartment, "Test Complex", grade=InvestmentGrade.A, roi_pct=12.0)
    deal.motivation_signs = ["срочно", "торг"]

    message = format_hunter_alert(deal)

    assert "Срочная сделка" in message
    assert "срочно" in message


def test_format_deal_message_alias() -> None:
    apartment = Apartment(
        external_id="123456",
        url="https://krisha.kz/a/show/123456",
        complex_id=1,
        price=80_000_000,
        price_per_sqm=800_000,
        district="Esil",
        address="Street",
        rooms=2,
        total_area=100.0,
    )
    deal = _make_deal(
        apartment,
        "Test Complex",
        grade=InvestmentGrade.A,
        roi_pct=12.0,
        recommendation="дисконт 20.0%; мотивация продавца (срочно)",
    )

    message = format_deal_message(deal)

    assert "Рейтинг: A" in message
    assert "ROI: ~12%" in message
    assert "дисконт 20.0%" in message


@pytest.mark.asyncio
async def test_notify_new_deals_sends_and_records(db_session: AsyncSession) -> None:
    suffix = uuid.uuid4().hex[:8]
    external_id = str(900_000_000 + int(suffix[:6], 16) % 99_000_000)
    complex_ = await complex_repo.get_or_create(db_session, f"Tower {suffix}")
    apartment, _, _ = await apartment_repo.upsert_apartment(
        db_session,
        {
            "external_id": external_id,
            "url": f"https://krisha.kz/a/show/{external_id}",
            "complex_id": complex_.id,
            "price": 80_000_000,
            "price_per_sqm": 800_000,
            "district": "Esil",
            "address": "Kabanbay 1",
            "rooms": 2,
            "total_area": 100.0,
        },
    )
    await db_session.flush()

    sender = AsyncMock(return_value=True)
    deal = _make_deal(apartment, complex_.name)
    sent = await notify_new_deals([deal], db_session, sender_fn=sender)

    assert sent == 1
    sender.assert_awaited_once()

    result = await db_session.execute(
        select(Notification).where(Notification.apartment_id == apartment.id),
    )
    notification = result.scalar_one()
    assert notification.notification_type == NOTIFICATION_TYPE_NEW_DEAL
    assert notification.is_sent is True
    assert "ЖК:" in notification.message


@pytest.mark.asyncio
async def test_notify_new_deals_skips_recent_duplicate(db_session: AsyncSession) -> None:
    suffix = uuid.uuid4().hex[:8]
    external_id = str(910_000_000 + int(suffix[:6], 16) % 89_000_000)
    complex_ = await complex_repo.get_or_create(db_session, f"Tower B {suffix}")
    apartment, _, _ = await apartment_repo.upsert_apartment(
        db_session,
        {
            "external_id": external_id,
            "url": f"https://krisha.kz/a/show/{external_id}",
            "complex_id": complex_.id,
            "price": 80_000_000,
            "price_per_sqm": 800_000,
            "district": "Esil",
            "address": "Kabanbay 2",
            "rooms": 2,
            "total_area": 100.0,
        },
    )
    db_session.add(
        Notification(
            apartment_id=apartment.id,
            notification_type=NOTIFICATION_TYPE_NEW_DEAL,
            message="previous",
            sent_at=datetime.now(UTC) - timedelta(hours=1),
            is_sent=True,
        ),
    )
    await db_session.flush()

    sender = AsyncMock(return_value=True)
    deal = _make_deal(apartment, complex_.name)
    sent = await notify_new_deals([deal], db_session, sender_fn=sender)

    assert sent == 0
    sender.assert_not_awaited()


@pytest.mark.asyncio
async def test_notify_new_deals_records_failed_send(db_session: AsyncSession) -> None:
    suffix = uuid.uuid4().hex[:8]
    external_id = str(920_000_000 + int(suffix[:6], 16) % 79_000_000)
    complex_ = await complex_repo.get_or_create(db_session, f"Tower C {suffix}")
    apartment, _, _ = await apartment_repo.upsert_apartment(
        db_session,
        {
            "external_id": external_id,
            "url": f"https://krisha.kz/a/show/{external_id}",
            "complex_id": complex_.id,
            "price": 80_000_000,
            "price_per_sqm": 800_000,
            "district": "Esil",
            "address": "Kabanbay 3",
            "rooms": 2,
            "total_area": 100.0,
        },
    )
    await db_session.flush()

    sender = AsyncMock(return_value=False)
    deal = _make_deal(apartment, complex_.name)
    sent = await notify_new_deals([deal], db_session, sender_fn=sender)

    assert sent == 0
    result = await db_session.execute(
        select(Notification).where(Notification.apartment_id == apartment.id),
    )
    notification = result.scalar_one()
    assert notification.is_sent is False
