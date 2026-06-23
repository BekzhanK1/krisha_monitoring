from __future__ import annotations

import html
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analyzer.deal_analyzer import Deal
from app.utils.fixture_data import is_fixture_apartment
from app.analyzer.investment_scorer import InvestmentGrade
from app.models import Notification
from app.scraper.urls import listing_url
from app.telegram.sender import send_alert

if TYPE_CHECKING:
    from app.analyzer.financial_model import DealFinancials

NOTIFICATION_TYPE_NEW_DEAL = "new_deal"
NOTIFICATION_TYPE_HUNTER_ALERT = "hunter_alert"
NOTIFICATION_TYPE_PRICE_DROP = "price_drop"

# Backward-compatible alias used by existing jobs/tests during migration.
NOTIFICATION_TYPE = NOTIFICATION_TYPE_NEW_DEAL

DEDUP_HOURS = 24
HUNTER_GRADES = frozenset({InvestmentGrade.A_PLUS, InvestmentGrade.A})


def format_price(price: int) -> str:
    return f"{price:,}".replace(",", " ")


def _format_price_mln(price: int) -> str:
    mln = price / 1_000_000
    if abs(mln - round(mln)) < 0.05:
        return f"{int(round(mln))} млн"
    return f"{mln:.1f} млн"


def _resolve_roi_pct(
    deal: Deal,
    financials: DealFinancials | None,
) -> float | None:
    if deal.roi_pct is not None:
        return deal.roi_pct
    if financials is not None:
        return financials.roi_pct
    return None


def _resolve_recommendation(deal: Deal) -> str:
    if deal.recommendation:
        return deal.recommendation
    if deal.motivation_signs:
        return f"Признаки мотивации: {', '.join(deal.motivation_signs)}"
    if deal.deal_reasons:
        return "; ".join(deal.deal_reasons[:2])
    return "Объект ниже медианы ЖК — стоит проверить детали."


def _format_link_line(apartment_url: str) -> str:
    safe_url = html.escape(apartment_url, quote=True)
    return f'Ссылка: <a href="{safe_url}">объявление</a>'


def _base_alert_lines(
    deal: Deal,
    *,
    financials: DealFinancials | None = None,
) -> list[str]:
    apartment = deal.apartment
    stats = deal.market_stats
    discount = f" (-{deal.discount_pct:.0f}%)"
    roi_pct = _resolve_roi_pct(deal, financials)

    lines = [
        f"ЖК: {html.escape(stats.complex_name)}",
        f"Цена: {_format_price_mln(apartment.price)}{discount}",
        f"Площадь: {apartment.total_area:.0f} м²",
    ]

    if deal.grade is not None:
        lines.append(f"Рейтинг: {html.escape(deal.grade.value)}")

    if roi_pct is not None:
        lines.append(f"ROI: ~{roi_pct:.0f}%")

    url = listing_url(apartment.external_id) or apartment.url
    lines.append(_format_link_line(url))
    lines.append(f"Рекомендация: {html.escape(_resolve_recommendation(deal))}")
    return lines


def format_deal_alert(
    deal: Deal,
    financials: DealFinancials | None = None,
    scored: object | None = None,
) -> str:
    """Standard alert for newly discovered deals (TZ §8 format)."""
    _ = scored
    return "\n".join(_base_alert_lines(deal, financials=financials))


def format_hunter_alert(
    deal: Deal,
    financials: DealFinancials | None = None,
    scored: object | None = None,
) -> str:
    """Urgent hunter alert for motivated / high-grade listings."""
    _ = scored
    lines = ["🔥 <b>Срочная сделка</b>", ""]
    if deal.motivation_signs:
        signs = html.escape(", ".join(deal.motivation_signs))
        lines.extend([f"Признаки: {signs}", ""])
    lines.extend(_base_alert_lines(deal, financials=financials))
    return "\n".join(lines)


def format_price_drop(
    deal: Deal,
    *,
    old_price: int,
    financials: DealFinancials | None = None,
) -> str:
    """Stub formatter for future price-drop notifications."""
    drop_pct = (old_price - deal.apartment.price) / old_price * 100 if old_price > 0 else 0.0
    header = (
        f"📉 <b>Снижение цены</b> ({drop_pct:.0f}%)\n"
        f"Было: {_format_price_mln(old_price)} → "
        f"Стало: {_format_price_mln(deal.apartment.price)}\n"
    )
    return header + "\n".join(_base_alert_lines(deal, financials=financials))


def format_deal_message(deal: Deal) -> str:
    """Backward-compatible alias."""
    return format_deal_alert(deal)


def is_hunter_candidate(deal: Deal, *, min_discount_pct: float = 10.0) -> bool:
    if deal.discount_pct < min_discount_pct:
        return False
    if deal.is_motivated_seller:
        return True
    return deal.grade in HUNTER_GRADES


async def _has_recent_notification(
    session: AsyncSession,
    apartment_id: int,
    notification_type: str,
) -> bool:
    cutoff = datetime.now(UTC) - timedelta(hours=DEDUP_HOURS)
    result = await session.execute(
        select(Notification.id).where(
            Notification.apartment_id == apartment_id,
            Notification.notification_type == notification_type,
            Notification.sent_at >= cutoff,
        ),
    )
    return result.scalar_one_or_none() is not None


async def _has_hunter_notification(session: AsyncSession, apartment_id: int) -> bool:
    result = await session.execute(
        select(Notification.id).where(
            Notification.apartment_id == apartment_id,
            Notification.notification_type == NOTIFICATION_TYPE_HUNTER_ALERT,
        ),
    )
    return result.scalar_one_or_none() is not None


async def notify_new_deals(
    deals: list[Deal],
    session: AsyncSession,
    sender_fn: Callable[[str], Awaitable[bool]] | None = None,
) -> int:
    """Send notifications for new deals. Returns count of successfully sent messages."""
    send = sender_fn or send_alert
    sent_count = 0

    for deal in deals:
        apartment_id = deal.apartment.id
        if is_fixture_apartment(deal.apartment):
            logger.debug("Skipping fixture apartment_id={} for new_deal", apartment_id)
            continue
        if await _has_recent_notification(session, apartment_id, NOTIFICATION_TYPE_NEW_DEAL):
            logger.debug("Skipping duplicate deal notification for apartment_id={}", apartment_id)
            continue

        message = format_deal_alert(deal)
        is_sent = await send(message)
        if is_sent:
            sent_count += 1

        session.add(
            Notification(
                apartment_id=apartment_id,
                notification_type=NOTIFICATION_TYPE_NEW_DEAL,
                message=message,
                sent_at=datetime.now(UTC),
                is_sent=is_sent,
            ),
        )

    if deals:
        await session.flush()

    return sent_count


async def notify_hunter_deals(
    deals: list[Deal],
    session: AsyncSession,
    sender_fn: Callable[[str], Awaitable[bool]] | None = None,
) -> int:
    """Send hunter alerts for urgent deals. Returns count of successfully sent messages."""
    send = sender_fn or send_alert
    sent_count = 0

    for deal in deals:
        apartment_id = deal.apartment.id
        if is_fixture_apartment(deal.apartment):
            logger.debug("Skipping fixture apartment_id={} for hunter_alert", apartment_id)
            continue
        if await _has_hunter_notification(session, apartment_id):
            logger.debug("Skipping duplicate hunter alert for apartment_id={}", apartment_id)
            continue

        message = format_hunter_alert(deal)
        is_sent = await send(message)
        if is_sent:
            sent_count += 1

        session.add(
            Notification(
                apartment_id=apartment_id,
                notification_type=NOTIFICATION_TYPE_HUNTER_ALERT,
                message=message,
                sent_at=datetime.now(UTC),
                is_sent=is_sent,
            ),
        )

    if deals:
        await session.flush()

    return sent_count
