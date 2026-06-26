"""Callback query handlers for inline keyboard navigation."""
from __future__ import annotations

import re

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from telegram import Update
from telegram.ext import ContextTypes

from app.analyzer.deal_analyzer import DealAnalyzer
from app.database import AsyncSessionLocal
from app.models import Apartment
from app.models.apartment_score import ApartmentScore
from app.repositories import apartment_repo, favorite_repo, score_repo
from app.repositories.apartment_filter import get_filtered_apartments
from app.repositories.search_config_repo import get_active_configs, get_or_create_default
from app.scraper.filters import SearchFilters
from app.scraper.urls import is_valid_listing_id
from app.telegram.cache import apartment_list_cache
from app.telegram.keyboards import (
    back_to_menu_keyboard,
    listing_detail_keyboard,
    listing_list_keyboard,
    main_menu_keyboard,
)
from app.telegram.listing_detail import format_apartment_detail
from app.telegram.pagination import ITEMS_PER_PAGE, paginate_items
from app.telegram.settings_handlers import reply_settings_overview

# Callback data patterns
MENU_PATTERN = re.compile(r"^menu$")
CMD_PATTERN = re.compile(r"^cmd:(\w+)$")
APT_PATTERN = re.compile(r"^apt:(\d+):([a-z_]+):(\d+)$")
FAV_PATTERN = re.compile(r"^fav:(\d+):(\d+)$")
NOOP_PATTERN = re.compile(r"^noop$")

# Prefixes for paginated listing callbacks
LIST_PREFIXES = {"filter", "fnew", "top", "new", "discount", "vip", "favorites"}


async def _get_or_create_user(update: Update, session: AsyncSession):
    user = update.effective_user
    if user is None:
        return None
    return await favorite_repo.get_or_create_user(
        session,
        telegram_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
    )


async def _get_active_filters(session: AsyncSession) -> SearchFilters:
    configs = await get_active_configs(session)
    if not configs:
        config = await get_or_create_default(session)
        return SearchFilters.from_search_config(config)
    return SearchFilters.from_search_config(configs[0])


async def _fetch_apartments(
    session: AsyncSession,
    list_type: str,
) -> list[Apartment]:
    """Fetch apartments for a given list type, with caching."""
    cache_key = f"apt_list:{list_type}"
    cached = await apartment_list_cache.get(cache_key)
    if cached is not None:
        return cached

    apartments: list[Apartment] = []

    if list_type == "filter":
        filters = await _get_active_filters(session)
        apartments = await get_filtered_apartments(session, filters, limit=50)
    elif list_type == "fnew":
        filters = await _get_active_filters(session)
        apartments = await get_filtered_apartments(session, filters, limit=50, recent_hours=24)
    elif list_type == "top":
        from sqlalchemy.orm import joinedload

        result = await session.execute(
            select(Apartment)
            .options(joinedload(Apartment.complex))
            .where(Apartment.is_active.is_(True), Apartment.external_id.regexp_match("^[0-9]+$"))
            .order_by(Apartment.price_per_sqm.asc())
            .limit(50),
        )
        apartments = [a for a in result.scalars().unique().all() if is_valid_listing_id(a.external_id)]
    elif list_type == "new":
        from datetime import UTC, datetime, timedelta

        from sqlalchemy.orm import joinedload

        cutoff = datetime.now(UTC) - timedelta(hours=24)
        result = await session.execute(
            select(Apartment)
            .options(joinedload(Apartment.complex))
            .where(
                Apartment.is_active.is_(True),
                Apartment.first_seen_at > cutoff,
                Apartment.external_id.regexp_match("^[0-9]+$"),
            )
            .order_by(Apartment.first_seen_at.desc())
            .limit(50),
        )
        apartments = [a for a in result.scalars().unique().all() if is_valid_listing_id(a.external_id)]
    elif list_type == "discount":
        analyzer = DealAnalyzer(session)
        deals = await analyzer.analyze_all_complexes()
        apartments = [
            deal.apartment
            for deal in deals
            if is_valid_listing_id(deal.apartment.external_id)
        ][:50]
    elif list_type == "vip":
        filters = await _get_active_filters(session)
        if await score_repo.has_scores(session):
            vip_rows = await score_repo.get_vip_apartments(session, filters, limit=50)
            apartments = [apt for apt, _ in vip_rows]
        else:
            analyzer = DealAnalyzer(session)
            deals = await analyzer.analyze_all_complexes()
            for deal in deals:
                if deal.grade is None or deal.grade.value not in {"A+", "A"}:
                    continue
                if not is_valid_listing_id(deal.apartment.external_id):
                    continue
                apartments.append(deal.apartment)
                if len(apartments) >= 50:
                    break

    await apartment_list_cache.set(cache_key, apartments)
    return apartments


async def _send_listing_list(
    update: Update,
    session: AsyncSession,
    list_type: str,
    page: int = 1,
) -> None:
    """Send or edit a paginated listing of apartments."""
    query = update.callback_query
    apartments = await _fetch_apartments(session, list_type)

    page_items, effective_page = paginate_items(apartments, page, ITEMS_PER_PAGE)
    apt_ids = [a.id for a in page_items]

    titles = {
        "filter": "🔍 По фильтру",
        "fnew": "🆕 Новые за 24ч (по фильтру)",
        "top": "📊 Все активные",
        "new": "🆕 Новые за 24ч",
        "discount": "📉 Выгодные сделки",
        "vip": "⭐ VIP объекты",
        "favorites": "⭐ Избранное",
    }
    title = titles.get(list_type, "📋 Список")

    if not page_items:
        text = f"{title}\n\nПока нет данных"
        keyboard = back_to_menu_keyboard()
    else:
        text = f"{title}\n\nВыберите объект для подробностей:"
        keyboard = listing_list_keyboard(
            prefix=list_type,
            apartment_ids=apt_ids,
            current_page=effective_page,
            total_items=len(apartments),
            back_callback="menu",
        )

    if query is not None:
        await query.answer()
        await query.edit_message_text(text, reply_markup=keyboard)
    elif update.effective_message is not None:
        await update.effective_message.reply_text(text, reply_markup=keyboard)


async def _send_apartment_detail(
    update: Update,
    session: AsyncSession,
    apartment_id: int,
    *,
    list_prefix: str = "filter",
    list_page: int = 1,
) -> None:
    """Send the detail view for a single apartment."""
    query = update.callback_query
    apartment = await apartment_repo.get_by_id_with_details(session, apartment_id)
    if apartment is None:
        if query is not None:
            await query.answer("Объект не найден", show_alert=True)
        return

    # Get score if available
    score = await score_repo.get_by_apartment_id(session, apartment_id)

    # Check favorite status
    user = await _get_or_create_user(update, session)
    is_fav = False
    if user is not None:
        is_fav = await favorite_repo.is_favorite(session, user.id, apartment_id)

    prices = list(apartment.prices) if apartment.prices else []
    text = format_apartment_detail(
        apartment,
        score=score,
        is_favorite=is_fav,
        prices=prices,
    )
    keyboard = listing_detail_keyboard(
        apartment_id,
        is_favorite=is_fav,
        back_callback=f"list:{list_prefix}:{list_page}",
    )

    if query is not None:
        await query.answer()
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=keyboard, disable_web_page_preview=True)
    elif update.effective_message is not None:
        await update.effective_message.reply_text(
            text, parse_mode="HTML", reply_markup=keyboard, disable_web_page_preview=True,
        )


async def _toggle_favorite(
    update: Update,
    session: AsyncSession,
    apartment_id: int,
    currently_fav: bool,
) -> None:
    """Toggle favorite status and refresh the detail view."""
    query = update.callback_query
    user = await _get_or_create_user(update, session)
    if user is None:
        if query is not None:
            await query.answer("Не удалось определить пользователя", show_alert=True)
        return

    if currently_fav:
        await favorite_repo.remove_favorite(session, user.id, apartment_id)
        await query.answer("💔 Удалено из избранного")
    else:
        await favorite_repo.add_favorite(session, user.id, apartment_id)
        await query.answer("⭐ Добавлено в избранное")

    await session.commit()
    # Refresh the detail view
    await _send_apartment_detail(update, session, apartment_id)


async def _send_favorites(
    update: Update,
    session: AsyncSession,
    page: int = 1,
) -> None:
    """Send paginated list of user's favorite apartments."""
    query = update.callback_query
    user = await _get_or_create_user(update, session)
    if user is None:
        return

    apartments = await favorite_repo.get_favorite_apartments(
        session, user.id, limit=50, offset=0,
    )
    page_items, effective_page = paginate_items(apartments, page, ITEMS_PER_PAGE)
    apt_ids = [a.id for a in page_items]

    if not page_items:
        text = "⭐ Избранное\n\nУ вас пока нет избранных объектов.\nНажмите «⭐ В избранное» на странице объекта."
        keyboard = back_to_menu_keyboard()
    else:
        text = "⭐ Избранное\n\nВыберите объект для подробностей:"
        keyboard = listing_list_keyboard(
            prefix="favorites",
            apartment_ids=apt_ids,
            current_page=effective_page,
            total_items=len(apartments),
            back_callback="menu",
        )

    if query is not None:
        await query.answer()
        await query.edit_message_text(text, reply_markup=keyboard)
    elif update.effective_message is not None:
        await update.effective_message.reply_text(text, reply_markup=keyboard)


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Main callback router for all inline keyboard interactions."""
    query = update.callback_query
    if query is None or query.data is None:
        return

    data = query.data
    user = update.effective_user
    user_id = user.id if user is not None else "unknown"
    logger.debug("Callback query data={} from user_id={}", data, user_id)

    try:
        async with AsyncSessionLocal() as session:
            # Menu button
            if MENU_PATTERN.match(data):
                await query.answer()
                await query.edit_message_text(
                    "🏠 <b>Главное меню</b>\n\nВыберите раздел:",
                    parse_mode="HTML",
                    reply_markup=main_menu_keyboard(),
                )
                return

            if NOOP_PATTERN.match(data):
                await query.answer()
                return

            # Command shortcuts from menu
            cmd_match = CMD_PATTERN.match(data)
            if cmd_match:
                cmd = cmd_match.group(1)
                if cmd == "settings":
                    await query.answer()
                    await reply_settings_overview(update, session)
                    return
                if cmd == "favorites":
                    await _send_favorites(update, session, page=1)
                    return
                if cmd in LIST_PREFIXES:
                    await _send_listing_list(update, session, cmd, page=1)
                    return
                # report / zhk — answer and let user use command
                await query.answer("Используйте команду для этого раздела")
                return

            # Paginated listing navigation: "list:<prefix>:<page>"
            if data.startswith("list:"):
                parts = data.split(":")
                if len(parts) == 3:
                    prefix = parts[1]
                    page = int(parts[2])
                    if prefix == "favorites":
                        await _send_favorites(update, session, page=page)
                    elif prefix in LIST_PREFIXES:
                        await _send_listing_list(update, session, prefix, page=page)
                    return

            # Direct pagination: "<prefix>:<page>" for list prefixes
            parts = data.split(":")
            if len(parts) == 2 and parts[0] in LIST_PREFIXES:
                prefix = parts[0]
                page = int(parts[1])
                if prefix == "favorites":
                    await _send_favorites(update, session, page=page)
                else:
                    await _send_listing_list(update, session, prefix, page=page)
                return

            # Apartment detail: "apt:<id>:<list_prefix>:<list_page>"
            apt_match = APT_PATTERN.match(data)
            if apt_match:
                apartment_id = int(apt_match.group(1))
                list_prefix = apt_match.group(2)
                list_page = int(apt_match.group(3))
                await _send_apartment_detail(
                    update, session, apartment_id,
                    list_prefix=list_prefix, list_page=list_page,
                )
                return

            # Favorite toggle: "fav:<apt_id>:<currently_fav>"
            fav_match = FAV_PATTERN.match(data)
            if fav_match:
                apartment_id = int(fav_match.group(1))
                currently_fav = bool(int(fav_match.group(2)))
                await _toggle_favorite(update, session, apartment_id, currently_fav)
                return

            await query.answer()
    except Exception:
        logger.exception("Error in callback handler data={} user_id={}", data, user_id)
        if query is not None:
            await query.answer("⚠️ Произошла ошибка", show_alert=True)
