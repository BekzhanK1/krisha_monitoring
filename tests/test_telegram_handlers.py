from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from telegram import Message, Update, User

from app.models import Apartment
from app.scraper.filters import SearchFilters
from app.telegram.handlers import (
    cmd_discount,
    cmd_new,
    cmd_report,
    cmd_start,
    cmd_top,
    cmd_vip,
    cmd_zhk,
)


def _make_update(user_id: int = 42) -> Update:
    update = MagicMock(spec=Update)
    update.effective_user = User(id=user_id, is_bot=False, first_name="Test")
    message = AsyncMock(spec=Message)
    message.reply_text = AsyncMock()
    update.message = message
    return update


@pytest.mark.asyncio
async def test_cmd_start_replies_with_welcome() -> None:
    update = _make_update()
    context = MagicMock()

    await cmd_start(update, context)

    update.message.reply_text.assert_awaited_once()
    text = update.message.reply_text.await_args.args[0]
    assert "Krisha Monitor" in text
    assert "/zhk" in text
    assert "/report" in text
    assert "/vip" in text


@pytest.mark.asyncio
async def test_cmd_top_returns_apartments(db_session: AsyncSession) -> None:
    suffix = uuid.uuid4().int % 900_000_000 + 100_000_000
    external_id = str(suffix)
    from app.repositories import apartment_repo, complex_repo

    complex_ = await complex_repo.get_or_create(db_session, f"Top Complex {suffix}")
    apartment, _, _ = await apartment_repo.upsert_apartment(
        db_session,
        {
            "external_id": external_id,
            "url": f"https://krisha.kz/a/show/{external_id}",
            "complex_id": complex_.id,
            "price": 50_000_000,
            "price_per_sqm": 400_000,
            "district": "Esil",
            "address": "Street",
            "rooms": 2,
            "total_area": 100.0,
        },
    )
    await db_session.flush()
    loaded = await db_session.execute(
        select(Apartment)
        .options(joinedload(Apartment.complex))
        .where(Apartment.id == apartment.id),
    )
    apt = loaded.scalar_one()

    mock_result = MagicMock()
    mock_result.scalars.return_value.unique.return_value.all.return_value = [apt]
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)

    update = _make_update()
    with patch("app.telegram.handlers.AsyncSessionLocal") as session_local:
        session_local.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        session_local.return_value.__aexit__ = AsyncMock(return_value=False)
        await cmd_top(update, MagicMock())

    reply_text = update.message.reply_text.await_args.args[0]
    assert "млн" in reply_text
    assert external_id in reply_text


@pytest.mark.asyncio
async def test_cmd_new_filters_recent_apartments(db_session: AsyncSession) -> None:
    suffix = uuid.uuid4().int % 900_000_000 + 100_000_000
    external_id = str(suffix)
    from app.repositories import apartment_repo, complex_repo

    complex_ = await complex_repo.get_or_create(db_session, f"New Complex {suffix}")
    apartment, _, _ = await apartment_repo.upsert_apartment(
        db_session,
        {
            "external_id": external_id,
            "url": f"https://krisha.kz/a/show/{external_id}",
            "complex_id": complex_.id,
            "price": 50_000_000,
            "price_per_sqm": 500_000,
            "district": "Esil",
            "address": "Street",
            "rooms": 2,
            "total_area": 100.0,
        },
    )
    apartment.first_seen_at = datetime.now(UTC) - timedelta(hours=1)
    await db_session.flush()

    update = _make_update()
    with patch("app.telegram.handlers.AsyncSessionLocal") as session_local:
        session_local.return_value.__aenter__ = AsyncMock(return_value=db_session)
        session_local.return_value.__aexit__ = AsyncMock(return_value=False)
        await cmd_new(update, MagicMock())

    reply_text = update.message.reply_text.await_args.args[0]
    assert "млн" in reply_text


@pytest.mark.asyncio
async def test_cmd_new_empty_reply() -> None:
    update = _make_update()
    empty_result = MagicMock()
    empty_result.scalars.return_value.unique.return_value.all.return_value = []

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=empty_result)

    with patch("app.telegram.handlers.AsyncSessionLocal") as session_local:
        session_local.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        session_local.return_value.__aexit__ = AsyncMock(return_value=False)
        await cmd_new(update, MagicMock())

    update.message.reply_text.assert_awaited_once_with("Пока нет данных")


@pytest.mark.asyncio
async def test_cmd_discount_uses_analyzer(db_session: AsyncSession) -> None:
    update = _make_update()
    mock_deals = []

    with (
        patch("app.telegram.handlers.AsyncSessionLocal") as session_local,
        patch("app.telegram.handlers.DealAnalyzer") as analyzer_cls,
    ):
        session_local.return_value.__aenter__ = AsyncMock(return_value=db_session)
        session_local.return_value.__aexit__ = AsyncMock(return_value=False)
        analyzer = analyzer_cls.return_value
        analyzer.analyze_all_complexes = AsyncMock(return_value=mock_deals)
        await cmd_discount(update, MagicMock())

    analyzer.analyze_all_complexes.assert_awaited_once()
    update.message.reply_text.assert_awaited_once_with("Пока нет данных")


@pytest.mark.asyncio
async def test_cmd_top_handles_errors() -> None:
    update = _make_update()
    with patch("app.telegram.handlers.AsyncSessionLocal") as session_local:
        session_local.side_effect = RuntimeError("db down")
        await cmd_top(update, MagicMock())

    update.message.reply_text.assert_awaited_once_with("⚠️ Произошла ошибка")


@pytest.mark.asyncio
async def test_cmd_zhk_top_list() -> None:
    update = _make_update()
    context = MagicMock()
    context.args = []

    with patch("app.telegram.handlers.AsyncSessionLocal") as session_local:
        mock_session = AsyncMock()
        session_local.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        session_local.return_value.__aexit__ = AsyncMock(return_value=False)
        with patch(
            "app.telegram.handlers.analytics_repo.get_top_complexes_by_active_count",
            AsyncMock(return_value=[("EXPO Residence", 42), ("Green City", 30)]),
        ):
            await cmd_zhk(update, context)

    reply_text = update.message.reply_text.await_args.args[0]
    assert "EXPO Residence" in reply_text
    assert "42" in reply_text
    assert update.message.reply_text.await_args.kwargs.get("parse_mode") == "HTML"


@pytest.mark.asyncio
async def test_cmd_zhk_search_shows_snapshot() -> None:
    from app.models.analytics import MarketAnalytics

    update = _make_update()
    context = MagicMock()
    context.args = ["EXPO"]

    complex_mock = MagicMock()
    complex_mock.id = 1
    complex_mock.name = "EXPO Residence"
    snapshot = MarketAnalytics(
        complex_id=1,
        median_price=28_000_000,
        avg_price=29_000_000,
        median_price_per_sqm=580_000,
        avg_price_per_sqm=590_000.0,
        active_count=42,
        sold_last_30d=8,
        avg_days_on_market=45.0,
    )

    with patch("app.telegram.handlers.AsyncSessionLocal") as session_local:
        mock_session = AsyncMock()
        session_local.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        session_local.return_value.__aexit__ = AsyncMock(return_value=False)
        with (
            patch(
                "app.telegram.handlers.complex_repo.search_by_name",
                AsyncMock(return_value=[complex_mock]),
            ),
            patch(
                "app.telegram.handlers.analytics_repo.get_latest_by_complex",
                AsyncMock(return_value=snapshot),
            ),
        ):
            await cmd_zhk(update, context)

    reply_text = update.message.reply_text.await_args.args[0]
    assert "EXPO Residence" in reply_text
    assert "42" in reply_text
    assert "8" in reply_text


@pytest.mark.asyncio
async def test_cmd_zhk_multiple_matches_asks_to_clarify() -> None:
    update = _make_update()
    context = MagicMock()
    context.args = ["Green"]

    matches = [MagicMock(), MagicMock()]
    matches[0].name = "Green City"
    matches[1].name = "Green Park"

    with patch("app.telegram.handlers.AsyncSessionLocal") as session_local:
        mock_session = AsyncMock()
        session_local.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        session_local.return_value.__aexit__ = AsyncMock(return_value=False)
        with patch(
            "app.telegram.handlers.complex_repo.search_by_name",
            AsyncMock(return_value=matches),
        ):
            await cmd_zhk(update, context)

    reply_text = update.message.reply_text.await_args.args[0]
    assert "Найдено несколько ЖК" in reply_text


@pytest.mark.asyncio
async def test_cmd_report_uses_days_arg() -> None:
    update = _make_update()
    context = MagicMock()
    context.args = ["14"]

    with patch("app.telegram.handlers.AsyncSessionLocal") as session_local:
        mock_session = AsyncMock()
        session_local.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        session_local.return_value.__aexit__ = AsyncMock(return_value=False)
        with patch(
            "app.telegram.handlers.build_market_report",
            AsyncMock(return_value="<b>report</b>"),
        ) as build_report:
            await cmd_report(update, context)

    build_report.assert_awaited_once_with(mock_session, days=14)
    update.message.reply_text.assert_awaited_once_with("<b>report</b>", parse_mode="HTML")


@pytest.mark.asyncio
async def test_cmd_vip_uses_score_repo() -> None:
    update = _make_update()
    context = MagicMock()
    context.args = []

    with patch("app.telegram.handlers.AsyncSessionLocal") as session_local:
        mock_session = AsyncMock()
        session_local.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        session_local.return_value.__aexit__ = AsyncMock(return_value=False)
        with (
            patch(
                "app.telegram.handlers._get_active_filters",
                AsyncMock(return_value=SearchFilters()),
            ),
            patch("app.telegram.handlers.score_repo.has_scores", AsyncMock(return_value=True)),
            patch(
                "app.telegram.handlers.score_repo.get_vip_apartments",
                AsyncMock(return_value=[]),
            ),
        ):
            await cmd_vip(update, context)

    update.message.reply_text.assert_awaited_once_with("Пока нет данных")


@pytest.mark.asyncio
async def test_cmd_vip_fallback_to_deal_analyzer() -> None:
    update = _make_update()
    context = MagicMock()
    context.args = []

    with (
        patch("app.telegram.handlers.AsyncSessionLocal") as session_local,
        patch("app.telegram.handlers.DealAnalyzer") as analyzer_cls,
        patch(
            "app.telegram.handlers._get_active_filters",
            AsyncMock(return_value=SearchFilters()),
        ),
        patch("app.telegram.handlers.score_repo.has_scores", AsyncMock(return_value=False)),
    ):
        mock_session = AsyncMock()
        session_local.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        session_local.return_value.__aexit__ = AsyncMock(return_value=False)
        analyzer = analyzer_cls.return_value
        analyzer.analyze_all_complexes = AsyncMock(return_value=[])
        await cmd_vip(update, context)

    analyzer.analyze_all_complexes.assert_awaited_once()
    update.message.reply_text.assert_awaited_once_with("Пока нет данных")
