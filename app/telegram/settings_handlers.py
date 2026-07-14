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
from app.repositories import search_config_complex_repo
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
SETTINGS_ADD_COMPLEX_KEY = "settings_add_complex"
CALLBACK_EDIT_PATTERN = re.compile(r"^edit:(\d+):([a-z_]+)$")
CALLBACK_DEL_COMPLEX_PATTERN = re.compile(r"^cdel:(\d+):(\d+)$")

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


def _format_complexes_lines(config: SearchConfig) -> list[str]:
    complexes = list(getattr(config, "complexes", []) or [])
    if not complexes and config.complex_id:
        return [_format_config_line("ЖК", config.complex_id)]
    if not complexes:
        return [_format_config_line("ЖК", None)]
    lines = [f"• ЖК ({len(complexes)}):"]
    for item in complexes:
        label = item.name.strip() if item.name and item.name.strip() else item.krisha_complex_id
        lines.append(f"  – {html.escape(label)} ({html.escape(item.krisha_complex_id)})")
    return lines


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
        *_format_complexes_lines(config),
    ]
    return "\n".join(lines)


def build_settings_keyboard(config: SearchConfig) -> InlineKeyboardMarkup:
    config_id = config.id
    buttons = [
        ("price_to", "Цена до"),
        ("rooms", "Комнаты"),
        ("area_from", "Площадь от"),
        ("area_to", "Площадь до"),
        ("text", "Текст"),
    ]
    keyboard: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                label,
                callback_data=f"edit:{config_id}:{field}",
            )
        ]
        for field, label in buttons
        if field in EDITABLE_FIELDS
    ]
    keyboard.append(
        [
            InlineKeyboardButton(
                "➕ Добавить ЖК",
                callback_data=f"edit:{config_id}:add_complex",
            )
        ]
    )
    for item in getattr(config, "complexes", []) or []:
        label = item.name.strip() if item.name and item.name.strip() else item.krisha_complex_id
        short = label if len(label) <= 28 else f"{label[:25]}…"
        keyboard.append(
            [
                InlineKeyboardButton(
                    f"🗑 {short}",
                    callback_data=f"cdel:{config_id}:{item.krisha_complex_id}",
                )
            ]
        )
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
        keyboard = build_settings_keyboard(configs[0])

    await message.reply_text(text, parse_mode="HTML", reply_markup=keyboard)


def parse_complex_input(raw: str) -> tuple[str, str | None] | None:
    """Parse ``12345`` or ``12345|EXPO Residence``."""
    text = raw.strip()
    if not text:
        return None
    if "|" in text:
        krisha_id, _, name = text.partition("|")
        krisha_id = krisha_id.strip()
        name = name.strip() or None
    else:
        parts = text.split(maxsplit=1)
        krisha_id = parts[0].strip()
        name = parts[1].strip() if len(parts) > 1 else None
    if not krisha_id.isdigit():
        return None
    return krisha_id, name


async def callback_settings_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data is None:
        return

    await query.answer()

    if not is_authorized_chat(update):
        if isinstance(query.message, Message):
            await query.message.reply_text(ACCESS_DENIED_MESSAGE)
        return

    del_match = CALLBACK_DEL_COMPLEX_PATTERN.match(query.data)
    if del_match is not None:
        config_id = int(del_match.group(1))
        krisha_id = del_match.group(2)
        try:
            async with AsyncSessionLocal() as session:
                removed = await search_config_complex_repo.remove_complex(
                    session,
                    config_id,
                    krisha_id,
                )
                await session.commit()
                configs = await get_active_configs(session)
                config = next((cfg for cfg in configs if cfg.id == config_id), None)
            if isinstance(query.message, Message):
                if not removed:
                    await query.message.reply_text("ЖК не найден в списке.")
                    return
                if config is None:
                    await query.message.reply_text("✅ ЖК удалён.")
                    return
                await query.message.reply_text(
                    f"✅ ЖК {html.escape(krisha_id)} удалён.\n\n{format_settings_message(config)}",
                    parse_mode="HTML",
                    reply_markup=build_settings_keyboard(config),
                )
        except Exception:
            logger.exception("Error deleting complex config_id={} id={}", config_id, krisha_id)
            if isinstance(query.message, Message):
                await query.message.reply_text(ERROR_MESSAGE)
        return

    match = CALLBACK_EDIT_PATTERN.match(query.data)
    if match is None:
        return

    config_id = int(match.group(1))
    field = match.group(2)

    if field == "add_complex":
        _user_data(context).pop(SETTINGS_EDIT_KEY, None)
        _user_data(context)[SETTINGS_ADD_COMPLEX_KEY] = {"config_id": config_id}
        if isinstance(query.message, Message):
            await query.message.reply_text(
                "Введите ID жилого комплекса с Krisha.\n"
                "Формат: <code>12345</code> или <code>12345|Название ЖК</code>\n\n"
                "ID берётся из URL поиска: <code>das[map.complex]=…</code>",
                parse_mode="HTML",
            )
        return

    if field not in EDITABLE_FIELDS:
        return

    _user_data(context).pop(SETTINGS_ADD_COMPLEX_KEY, None)
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
                from app.telegram.cache import apartment_list_cache
                from app.telegram.filter_editor import _get_config, _send_filter_editor

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

    # Handle complex add from filter editor
    filter_complex_state = user_data.get("filter_complex_input")
    if isinstance(filter_complex_state, dict):
        message = update.message
        if message is None or message.text is None:
            return
        config_id = filter_complex_state.get("config_id")
        if not isinstance(config_id, int):
            user_data.pop("filter_complex_input", None)
            return
        parsed = parse_complex_input(message.text)
        if parsed is None:
            await message.reply_text(
                "Неверный формат. Нужен числовой ID, например:\n"
                "<code>12345</code> или <code>12345|EXPO Residence</code>",
                parse_mode="HTML",
            )
            return
        krisha_id, name = parsed
        try:
            async with AsyncSessionLocal() as session:
                from app.telegram.cache import apartment_list_cache
                from app.telegram.filter_editor import _send_filter_editor

                await search_config_complex_repo.add_complex(
                    session,
                    config_id,
                    krisha_id,
                    name=name,
                )
                await session.commit()
                await apartment_list_cache.clear()
                user_data.pop("filter_complex_input", None)
                await message.reply_text(
                    f"✅ ЖК добавлен: {html.escape(name or krisha_id)} "
                    f"(<code>{html.escape(krisha_id)}</code>)",
                    parse_mode="HTML",
                )
                await _send_filter_editor(update, session)
        except Exception:
            logger.exception("Error adding complex from filter editor")
            await message.reply_text(ERROR_MESSAGE)
        return

    add_complex_state = user_data.get(SETTINGS_ADD_COMPLEX_KEY)
    if isinstance(add_complex_state, dict):
        message = update.message
        if message is None or message.text is None:
            return
        if not is_authorized_chat(update):
            user_data.pop(SETTINGS_ADD_COMPLEX_KEY, None)
            await message.reply_text(ACCESS_DENIED_MESSAGE)
            return

        config_id = add_complex_state.get("config_id")
        if not isinstance(config_id, int):
            user_data.pop(SETTINGS_ADD_COMPLEX_KEY, None)
            return

        parsed = parse_complex_input(message.text)
        if parsed is None:
            await message.reply_text(
                "Неверный формат. Нужен числовой ID, например:\n"
                "<code>12345</code>\n"
                "или\n"
                "<code>12345|EXPO Residence</code>",
                parse_mode="HTML",
            )
            return

        krisha_id, name = parsed
        try:
            async with AsyncSessionLocal() as session:
                await search_config_complex_repo.add_complex(
                    session,
                    config_id,
                    krisha_id,
                    name=name,
                )
                await session.commit()
                configs = await get_active_configs(session)
                config = next((cfg for cfg in configs if cfg.id == config_id), None)
            user_data.pop(SETTINGS_ADD_COMPLEX_KEY, None)
            if config is None:
                await message.reply_text(f"✅ ЖК {krisha_id} добавлен.")
                return
            label = name or krisha_id
            filters = SearchFilters.from_search_config(config)
            preview_urls = filters.build_urls()
            preview_lines = "\n".join(
                f'🔗 <a href="{html.escape(url, quote=True)}">поиск {index}</a>'
                for index, url in enumerate(preview_urls, start=1)
            )
            await message.reply_text(
                f"✅ Добавлен ЖК: <b>{html.escape(label)}</b> ({html.escape(krisha_id)})\n\n"
                f"{format_settings_message(config)}\n\n{preview_lines}",
                parse_mode="HTML",
                reply_markup=build_settings_keyboard(config),
            )
        except Exception:
            logger.exception("Error adding complex config_id={}", config_id)
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
            reply_markup=build_settings_keyboard(config),
        )
    except Exception:
        logger.exception("Error saving settings field={} config_id={}", field, config_id)
        await message.reply_text(ERROR_MESSAGE)
