from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analyzer.deal_analyzer import Deal
from app.models import Notification
from app.scraper.urls import listing_url
from app.telegram.sender import send_alert

NOTIFICATION_TYPE = "deal_alert"
DEDUP_HOURS = 24


def format_price(price: int) -> str:
    return f"{price:,}".replace(",", " ")


def format_deal_message(deal: Deal) -> str:
    apartment = deal.apartment
    stats = deal.market_stats
    floor_part = ""
    if apartment.floor is not None and apartment.total_floors is not None:
        floor_part = f"{apartment.floor}/{apartment.total_floors} эт"
    elif apartment.floor is not None:
        floor_part = f"{apartment.floor} эт"

    address_parts = [part for part in (apartment.district, apartment.address) if part]
    address_line = ", ".join(address_parts) if address_parts else "—"

    lines = [
        f"🏢 <b>{stats.complex_name}</b>",
        "",
        f"💰 <b>{format_price(apartment.price)} ₸</b> (-{deal.discount_pct:.0f}% от рынка)",
        f"📐 {apartment.total_area:.0f} м² | {apartment.rooms} комн | {floor_part}",
        f"📍 {address_line}",
        "",
        f"🏷 Дисконт: {deal.discount_pct:.0f}% ниже медианы",
    ]

    if deal.motivation_signs:
        lines.append(f"⚡️ Признаки: {', '.join(deal.motivation_signs)}")

    url = listing_url(apartment.external_id) or apartment.url
    lines.extend(
        [
            "",
            f'🔗 <a href="{url}">Смотреть объявление</a>',
        ],
    )
    return "\n".join(lines)


async def _has_recent_notification(session: AsyncSession, apartment_id: int) -> bool:
    cutoff = datetime.now(UTC) - timedelta(hours=DEDUP_HOURS)
    result = await session.execute(
        select(Notification.id).where(
            Notification.apartment_id == apartment_id,
            Notification.notification_type == NOTIFICATION_TYPE,
            Notification.sent_at >= cutoff,
        ),
    )
    return result.scalar_one_or_none() is not None


async def notify_new_deals(
    deals: list[Deal],
    session: AsyncSession,
    sender_fn: Callable[[str], Awaitable[bool]] = send_alert,
) -> int:
    """Send notifications for new deals. Returns count of successfully sent messages."""
    sent_count = 0

    for deal in deals:
        apartment_id = deal.apartment.id
        if await _has_recent_notification(session, apartment_id):
            logger.debug("Skipping duplicate deal notification for apartment_id={}", apartment_id)
            continue

        message = format_deal_message(deal)
        is_sent = await sender_fn(message)
        if is_sent:
            sent_count += 1

        session.add(
            Notification(
                apartment_id=apartment_id,
                notification_type=NOTIFICATION_TYPE,
                message=message,
                sent_at=datetime.now(UTC),
                is_sent=is_sent,
            ),
        )

    if deals:
        await session.commit()

    return sent_count
