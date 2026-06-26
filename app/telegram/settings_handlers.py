from __future__ import annotations

import html
import re

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Message, Update
from telegram.ext import ContextTypes

from app.config import get_settings
from app.database import AsyncSessionLocal
from app.models.search_config import SearchConfig
from app.repositories.search_config_repo import get_active_configs, update_field
from app.scraper.filters import SearchFilters
from app.telegram.notifications import format_price
from app.telegram.settings_validation import (
    CLEAR_VALUE,
    EDITABLE_FIELDS,
    FIELD_LABELS,
    validate_field_value,
)

SETTINGS_EDIT_KEY = "settings_edit"
CALLBACK_PATTERN = re.compile(r"^edit:(\d+):([a-z_]+)$")

ERROR_MESSAGE = "⚠️ Произошла ошибка"
ACCESS_DENIED_MESSAGE = "⛔ Редактирование доступно только владельцу бота."


def _user_data(context: ContextTypes.DEFAULT_TYPE) -> dict[str, object]:
    if context.user_data is None:
        context.user_data = {}
    return context.user_data


def is_authorized_chat(update: Update) -> bool:
    settings = get_settings()
    if settings.telegram_chat_id == 0:
        return False
    chat = update.effective_chat
    return chat is not None and chat.id == settings.telegram_chat_id


def _format_config_line(name: str, value: object) -> str:
    if value is None:
        return f"• {name}: —"
    return f"• {name}: {html.escape(str(value))}"


def format_settings_message(config: SearchConfig) -> str:
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
    return "\n".join(lines)


def build_settings_keyboard(config_id: int) -> InlineKeyboardMarkup:
    buttons = [
        ("price_to", "Цена до"),
        ("rooms", "Комнаты"),
        ("area_from", "Площадь от"),
        ("area_to", "Площадь до"),
        ("text", "Текст"),
    ]
    keyboard = [
        [
            InlineKeyboardButton(
                label,
                callback_data=f"edit:{config_id}:{field}",
            )
        ]
        for field, label in buttons
        if field in EDITABLE_FIELDS
    ]
    return InlineKeyboardMarkup(keyboard)


async def reply_settings_overview(
    update: Update,
    session: AsyncSession,
    *,
    prefix: str | None = None,
) -> None:
    message = update.effective_message
    if message is None:
        return

    configs = await get_active_configs(session)
    if not configs:
        await message.reply_text("Пока нет данных")
        return

    blocks = [format_settings_message(config) for config in configs]
    text = "\n\n".join(blocks)
    if prefix:
        text = f"{prefix}\n\n{text}"

    keyboard = None
    if is_authorized_chat(update) and len(configs) == 1:
        keyboard = build_settings_keyboard(configs[0].id)

    await message.reply_text(text, parse_mode="HTML", reply_markup=keyboard)


async def callback_settings_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data is None:
        return

    await query.answer()

    if not is_authorized_chat(update):
        if isinstance(query.message, Message):
            await query.message.reply_text(ACCESS_DENIED_MESSAGE)
        return

    match = CALLBACK_PATTERN.match(query.data)
    if match is None:
        return

    config_id = int(match.group(1))
    field = match.group(2)
    if field not in EDITABLE_FIELDS:
        return

    _user_data(context)[SETTINGS_EDIT_KEY] = {"config_id": config_id, "field": field}
    label = FIELD_LABELS[field]
    hint = f"Для сброса отправьте «{CLEAR_VALUE}»."
    if isinstance(query.message, Message):
        await query.message.reply_text(f"Введите новое значение для «{label}».\n{hint}")


async def handle_settings_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_data = _user_data(context)

    # Handle filter text input from the inline filter editor
    if user_data.get("filter_text_input"):
        user_data.pop("filter_text_input", None)
        message = update.message
        if message is None or message.text is None:
            return
        text_value = message.text.strip()
        try:
            async with AsyncSessionLocal() as session:
                from app.telegram.filter_editor import _get_config, _send_filter_editor
                from app.telegram.cache import apartment_list_cache

                config = await _get_config(session)
                if text_value == "-" or not text_value:
                    await update_field(session, config.id, "text", None)
                else:
                    await update_field(session, config.id, "text", text_value)
                await session.commit()
                await apartment_list_cache.clear()
                await _send_filter_editor(update, session)
        except Exception:
            logger.exception("Error saving filter text input")
            if message is not None:
                await message.reply_text(ERROR_MESSAGE)
        return

    edit_state = user_data.get(SETTINGS_EDIT_KEY)
    if not isinstance(edit_state, dict):
        return

    message = update.message
    if message is None or message.text is None:
        return

    if not is_authorized_chat(update):
        user_data.pop(SETTINGS_EDIT_KEY, None)
        await message.reply_text(ACCESS_DENIED_MESSAGE)
        return

    field = edit_state.get("field")
    config_id = edit_state.get("config_id")
    if not isinstance(field, str) or not isinstance(config_id, int):
        user_data.pop(SETTINGS_EDIT_KEY, None)
        return

    try:
        async with AsyncSessionLocal() as session:
            configs = await get_active_configs(session)
            current = next((cfg for cfg in configs if cfg.id == config_id), None)
            value, error = validate_field_value(
                field,
                message.text,
                area_from=current.area_from if current is not None else None,
                area_to=current.area_to if current is not None else None,
            )
            if error is not None:
                await message.reply_text(error)
                return

            config = await update_field(session, config_id, field, value)
            await session.commit()

        user_data.pop(SETTINGS_EDIT_KEY, None)
        label = FIELD_LABELS[field]
        preview_url = SearchFilters.from_search_config(config).build_url()
        safe_url = html.escape(preview_url, quote=True)
        body = format_settings_message(config)
        await message.reply_text(
            f"✅ Сохранено: <b>{html.escape(label)}</b>\n\n{body}\n\n"
            f'🔗 <a href="{safe_url}">Превью поиска</a>',
            parse_mode="HTML",
            reply_markup=build_settings_keyboard(config.id),
        )
    except Exception:
        logger.exception("Error saving settings field={} config_id={}", field, config_id)
        await message.reply_text(ERROR_MESSAGE)
