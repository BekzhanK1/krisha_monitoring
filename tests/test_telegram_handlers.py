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
from app.telegram.handlers import cmd_discount, cmd_new, cmd_start, cmd_top


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
    assert "Krisha Monitor" in update.message.reply_text.await_args.args[0]


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
