from __future__ import annotations

import html
from datetime import UTC, datetime, timedelta

from loguru import logger
from sqlalchemy import ColumnElement, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from telegram import Update
from telegram.ext import ContextTypes

from app.analyzer.deal_analyzer import DealAnalyzer
from app.database import AsyncSessionLocal
from app.models import Apartment
from app.repositories.apartment_filter import get_filtered_apartments
from app.repositories.search_config_repo import get_active_configs, get_or_create_default
from app.scraper.filters import SearchFilters
from app.scraper.urls import is_valid_listing_id, listing_url
from app.telegram.notifications import format_price

ERROR_MESSAGE = "⚠️ Произошла ошибка"
NO_DATA_MESSAGE = "Пока нет данных"
MAX_ITEMS = 5


def _valid_apartment_filter() -> ColumnElement[bool]:
    return Apartment.external_id.regexp_match("^[0-9]+$")


def _build_cards(
    apartments: list[Apartment],
    *,
    discount_by_id: dict[int, float] | None = None,
) -> list[str]:
    cards: list[str] = []
    for apartment in apartments:
        if not is_valid_listing_id(apartment.external_id):
            continue
        discount = discount_by_id.get(apartment.id) if discount_by_id else None
        card = _format_apartment_card(apartment, discount)
        if card:
            cards.append(card)
        if len(cards) >= MAX_ITEMS:
            break
    return cards


def _format_floor(apartment: Apartment) -> str:
    if apartment.floor is not None and apartment.total_floors is not None:
        return f"{apartment.floor}/{apartment.total_floors}"
    if apartment.floor is not None:
        return str(apartment.floor)
    return "—"


def _format_apartment_card(
    apartment: Apartment,
    discount_pct: float | None = None,
    *,
    complex_name: str | None = None,
) -> str:
    name = complex_name or (apartment.complex.name if apartment.complex is not None else "—")
    price_mln = apartment.price / 1_000_000
    discount = f" (-{discount_pct:.0f}%)" if discount_pct is not None else ""
    floor = _format_floor(apartment)
    url = listing_url(apartment.external_id)
    if url is None:
        return ""
    safe_url = html.escape(url, quote=True)
    return (
        f"🏢 {html.escape(name)} | 💰 {price_mln:.0f} млн{discount} | "
        f"{apartment.total_area:.0f}м² | {floor} | "
        f'<a href="{safe_url}">объявление</a>'
    )


def _format_config_line(name: str, value: object) -> str:
    if value is None:
        return f"• {name}: —"
    return f"• {name}: {html.escape(str(value))}"


async def _reply_with_cards(
    update: Update,
    cards: list[str],
    *,
    empty_message: str = NO_DATA_MESSAGE,
) -> None:
    if update.message is None:
        return
    if not cards:
        await update.message.reply_text(empty_message)
        return
    await update.message.reply_text("\n\n".join(cards), parse_mode="HTML")


async def _with_session(handler_name: str, update: Update, work) -> None:  # type: ignore[no-untyped-def]
    user = update.effective_user
    user_id = user.id if user is not None else "unknown"
    logger.info("Telegram command /{} from user_id={}", handler_name, user_id)

    if update.message is None:
        return

    try:
        async with AsyncSessionLocal() as session:
            await work(session)
    except Exception:
        logger.exception("Error in /{} handler for user_id={}", handler_name, user_id)
        await update.message.reply_text(ERROR_MESSAGE)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    user = update.effective_user
    user_id = user.id if user is not None else "unknown"
    logger.info("Telegram command /start from user_id={}", user_id)
    await update.message.reply_text(
        "Krisha Monitor запущен\n\n"
        "Команды:\n"
        "/filter — по текущим настройкам\n"
        "/fnew — новые за 24ч по настройкам\n"
        "/top — все активные (без фильтра)\n"
        "/new — все новые за 24ч\n"
        "/discount — выгодные сделки\n"
        "/settings — текущие настройки",
    )


async def cmd_top(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async def work(session: AsyncSession) -> None:
        result = await session.execute(
            select(Apartment)
            .options(joinedload(Apartment.complex))
            .where(Apartment.is_active.is_(True), _valid_apartment_filter())
            .order_by(Apartment.price_per_sqm.asc())
            .limit(10),
        )
        apartments = list(result.scalars().unique().all())
        await _reply_with_cards(update, _build_cards(apartments))

    await _with_session("top", update, work)


async def cmd_new(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async def work(session: AsyncSession) -> None:
        cutoff = datetime.now(UTC) - timedelta(hours=24)
        result = await session.execute(
            select(Apartment)
            .options(joinedload(Apartment.complex))
            .where(
                Apartment.is_active.is_(True),
                Apartment.first_seen_at > cutoff,
                _valid_apartment_filter(),
            )
            .order_by(Apartment.first_seen_at.desc())
            .limit(10),
        )
        apartments = list(result.scalars().unique().all())
        await _reply_with_cards(update, _build_cards(apartments))

    await _with_session("new", update, work)


async def _get_active_filters(session: AsyncSession) -> SearchFilters:
    configs = await get_active_configs(session)
    if not configs:
        config = await get_or_create_default(session)
        return SearchFilters.from_search_config(config)
    return SearchFilters.from_search_config(configs[0])


async def cmd_filter(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async def work(session: AsyncSession) -> None:
        filters = await _get_active_filters(session)
        apartments = await get_filtered_apartments(session, filters, limit=10)
        await _reply_with_cards(update, _build_cards(apartments))

    await _with_session("filter", update, work)


async def cmd_fnew(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async def work(session: AsyncSession) -> None:
        filters = await _get_active_filters(session)
        apartments = await get_filtered_apartments(
            session,
            filters,
            limit=10,
            recent_hours=24,
        )
        await _reply_with_cards(update, _build_cards(apartments))

    await _with_session("fnew", update, work)


async def cmd_discount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async def work(session: AsyncSession) -> None:
        analyzer = DealAnalyzer(session)
        deals = await analyzer.analyze_all_complexes()
        cards = [
            _format_apartment_card(
                deal.apartment,
                deal.discount_pct,
                complex_name=deal.market_stats.complex_name,
            )
            for deal in deals
            if is_valid_listing_id(deal.apartment.external_id)
        ][:MAX_ITEMS]
        cards = [card for card in cards if card]
        await _reply_with_cards(update, cards)

    await _with_session("discount", update, work)


async def cmd_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async def work(session: AsyncSession) -> None:
        configs = await get_active_configs(session)
        if not configs:
            await _reply_with_cards(update, [], empty_message=NO_DATA_MESSAGE)
            return

        blocks: list[str] = []
        for config in configs:
            lines = [
                f"<b>{html.escape(config.name)}</b>",
                _format_config_line("город", config.city),
                _format_config_line("комнаты", config.rooms),
                _format_config_line(
                    "цена от",
                    format_price(config.price_from) if config.price_from else None,
                ),
                _format_config_line(
                    "цена до",
                    format_price(config.price_to) if config.price_to else None,
                ),
                _format_config_line("этаж от", config.floor_from),
                _format_config_line("этаж до", config.floor_to),
                _format_config_line("площадь от", config.area_from),
                _format_config_line("площадь до", config.area_to),
                _format_config_line("текст", config.text),
                _format_config_line("ЖК id", config.complex_id),
            ]
            blocks.append("\n".join(lines))

        if update.message is not None:
            await update.message.reply_text("\n\n".join(blocks), parse_mode="HTML")

    await _with_session("settings", update, work)
