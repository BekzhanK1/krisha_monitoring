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
from app.analyzer.report_builder import build_market_report
from app.database import AsyncSessionLocal
from app.models import Apartment
from app.models.analytics import MarketAnalytics
from app.models.residential_complex import ResidentialComplex
from app.repositories import analytics_repo, complex_repo, score_repo
from app.repositories.apartment_filter import get_filtered_apartments
from app.repositories.search_config_repo import get_active_configs, get_or_create_default
from app.scraper.filters import SearchFilters
from app.scraper.urls import is_valid_listing_id, listing_url
from app.telegram.settings_handlers import reply_settings_overview

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
    grade: str | None = None,
    roi_pct: float | None = None,
) -> str:
    name = complex_name or (apartment.complex.name if apartment.complex is not None else "—")
    price_mln = apartment.price / 1_000_000
    discount = f" (-{discount_pct:.0f}%)" if discount_pct is not None else ""
    floor = _format_floor(apartment)
    url = listing_url(apartment.external_id)
    if url is None:
        return ""
    safe_url = html.escape(url, quote=True)
    score_part = ""
    if grade is not None:
        score_part = f"⭐ {html.escape(grade)}"
        if roi_pct is not None:
            score_part += f" | ROI {roi_pct:.0f}%"
        score_part += " | "
    return (
        f"{score_part}🏢 {html.escape(name)} | 💰 {price_mln:.0f} млн{discount} | "
        f"{apartment.total_area:.0f}м² | {floor} | "
        f'<a href="{safe_url}">объявление</a>'
    )


def _format_zhk_snapshot(name: str, snapshot: MarketAnalytics) -> str:
    median_mln = snapshot.median_price / 1_000_000
    median_sqm_k = snapshot.median_price_per_sqm / 1_000
    days_str = (
        f"{snapshot.avg_days_on_market:.0f} дней"
        if snapshot.avg_days_on_market is not None
        else "—"
    )
    return (
        f"🏢 <b>{html.escape(name)}</b>\n"
        f"💰 Медиана: {median_mln:.0f} млн | {median_sqm_k:.0f}k/м²\n"
        f"📊 Активных: {snapshot.active_count} | Продано за 30д: {snapshot.sold_last_30d}\n"
        f"⏱ Среднее на рынке: {days_str}"
    )


def _format_zhk_top_list(rows: list[tuple[str, int]]) -> str:
    lines = ["<b>🏢 Топ ЖК по активным объявлениям</b>", ""]
    for index, (name, active_count) in enumerate(rows, start=1):
        lines.append(f"{index}. {html.escape(name)} — {active_count}")
    return "\n".join(lines)


def _parse_report_days(context: ContextTypes.DEFAULT_TYPE) -> int:
    if not context.args:
        return 7
    try:
        days = int(context.args[0])
    except ValueError:
        return 7
    return days if days > 0 else 7


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
        "/zhk — статистика по ЖК\n"
        "/report — сводный отчёт по рынку\n"
        "/vip — топ инвестиционных объектов\n"
        "/settings — настройки поиска (редактирование кнопками)",
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
                grade=deal.grade.value if deal.grade is not None else None,
                roi_pct=deal.roi_pct,
            )
            for deal in deals
            if is_valid_listing_id(deal.apartment.external_id)
        ][:MAX_ITEMS]
        cards = [card for card in cards if card]
        await _reply_with_cards(update, cards)

    await _with_session("discount", update, work)


async def cmd_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async def work(session: AsyncSession) -> None:
        await reply_settings_overview(update, session)

    await _with_session("settings", update, work)


async def cmd_zhk(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async def work(session: AsyncSession) -> None:
        if update.message is None:
            return

        if not context.args:
            rows = await analytics_repo.get_top_complexes_by_active_count(session, limit=10)
            if not rows:
                await update.message.reply_text(NO_DATA_MESSAGE)
                return
            await update.message.reply_text(
                _format_zhk_top_list(rows),
                parse_mode="HTML",
            )
            return

        query = " ".join(context.args).strip()
        matches: list[ResidentialComplex] = []
        if query.isdigit():
            complex_ = await complex_repo.get_by_id(session, int(query))
            if complex_ is not None:
                matches = [complex_]
        if not matches:
            matches = await complex_repo.search_by_name(session, query)

        if not matches:
            await update.message.reply_text(NO_DATA_MESSAGE)
            return
        if len(matches) > 1:
            names = ", ".join(html.escape(item.name) for item in matches[:5])
            await update.message.reply_text(
                f"Найдено несколько ЖК: {names}. Уточните название.",
                parse_mode="HTML",
            )
            return

        complex_ = matches[0]
        snapshot = await analytics_repo.get_latest_by_complex(session, complex_.id)
        if snapshot is None:
            await update.message.reply_text(NO_DATA_MESSAGE)
            return
        await update.message.reply_text(
            _format_zhk_snapshot(complex_.name, snapshot),
            parse_mode="HTML",
        )

    await _with_session("zhk", update, work)


async def cmd_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    days = _parse_report_days(context)

    async def work(session: AsyncSession) -> None:
        if update.message is None:
            return
        report = await build_market_report(session, days=days)
        await update.message.reply_text(report, parse_mode="HTML")

    await _with_session("report", update, work)


async def cmd_vip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async def work(session: AsyncSession) -> None:
        filters = await _get_active_filters(session)
        cards: list[str] = []

        if await score_repo.has_scores(session):
            vip_rows = await score_repo.get_vip_apartments(session, filters, limit=MAX_ITEMS)
            cards = [
                _format_apartment_card(
                    apartment,
                    score.discount_pct,
                    grade=score.grade,
                    roi_pct=score.roi_pct,
                )
                for apartment, score in vip_rows
            ]
            cards = [card for card in cards if card]
        else:
            analyzer = DealAnalyzer(session)
            deals = await analyzer.analyze_all_complexes()
            for deal in deals:
                if deal.grade is None or deal.grade.value not in {"A+", "A"}:
                    continue
                if not is_valid_listing_id(deal.apartment.external_id):
                    continue
                card = _format_apartment_card(
                    deal.apartment,
                    deal.discount_pct,
                    complex_name=deal.market_stats.complex_name,
                    grade=deal.grade.value,
                    roi_pct=deal.roi_pct,
                )
                if card:
                    cards.append(card)
                if len(cards) >= MAX_ITEMS:
                    break

        await _reply_with_cards(update, cards)

    await _with_session("vip", update, work)
