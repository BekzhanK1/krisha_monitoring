"""Inline filter editor for search configs.

Allows users to adjust all search parameters directly via inline keyboard buttons
without typing commands.  Supports:
  - Quick-select for rooms (1/2/3/4+)
  - +/- steppers for price, area, floor
  - Clear individual fields
  - Text search input
"""
from __future__ import annotations

import html
import re

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.database import AsyncSessionLocal
from app.models.search_config import SearchConfig
from app.repositories.search_config_repo import get_active_configs, get_or_create_default, update_field
from app.scraper.filters import SearchFilters
from app.telegram.notifications import format_price

# Callback data patterns
FILTER_MENU_PATTERN = re.compile(r"^fmenu$")
FILTER_FIELD_PATTERN = re.compile(r"^ffield:([a-z_]+)$")
FILTER_SET_PATTERN = re.compile(r"^fset:([a-z_]+):(.+)$")
FILTER_CLEAR_PATTERN = re.compile(r"^fclear:([a-z_]+)$")
FILTER_TEXT_PATTERN = re.compile(r"^ftext$")

# All editable filter fields with their display labels
FILTER_FIELDS: dict[str, str] = {
    "rooms": "🚪 Комнаты",
    "price_from": "💰 Цена от",
    "price_to": "💰 Цена до",
    "area_from": "📐 Площадь от",
    "area_to": "📐 Площадь до",
    "floor_from": "🏢 Этаж от",
    "floor_to": "🏢 Этаж до",
    "text": "📝 Текст",
}

# Stepper configurations: field -> (min, max, step)
STEPPERS: dict[str, tuple[int | float, int | float, int | float]] = {
    "price_from": (1_000_000, 500_000_000, 1_000_000),
    "price_to": (1_000_000, 500_000_000, 1_000_000),
    "area_from": (10.0, 500.0, 5.0),
    "area_to": (10.0, 500.0, 5.0),
    "floor_from": (1, 30, 1),
    "floor_to": (1, 30, 1),
}

# Room options
ROOM_OPTIONS = [1, 2, 3, 4]


def _format_field_value(config: SearchConfig, field: str) -> str:
    """Format a field's current value for display."""
    value = getattr(config, field, None)
    if value is None:
        return "—"
    if field in {"price_from", "price_to"}:
        return format_price(int(value))
    if field in {"area_from", "area_to"}:
        return f"{float(value):.0f} м²"
    if field == "rooms":
        return f"{int(value)} комн."
    if field in {"floor_from", "floor_to"}:
        return f"{int(value)} эт."
    if field == "text":
        return html.escape(str(value))
    return str(value)


def format_filter_editor_message(config: SearchConfig) -> str:
    """Format the filter editor overview message."""
    lines = ["⚙️ <b>Настройки фильтра</b>", ""]
    for field, label in FILTER_FIELDS.items():
        value = _format_field_value(config, field)
        lines.append(f"{label}: <b>{value}</b>")
    lines.append("")
    lines.append("Нажмите на поле, чтобы изменить его.")
    lines.append("💡 Текст: отправьте «-» для сброса.")
    return "\n".join(lines)


def build_filter_editor_keyboard(config: SearchConfig) -> InlineKeyboardMarkup:
    """Build the main filter editor keyboard — one button per field."""
    keyboard: list[list[InlineKeyboardButton]] = []

    # Rooms — quick select row
    current_rooms = config.rooms
    room_buttons: list[InlineKeyboardButton] = []
    for room in ROOM_OPTIONS:
        label = f"{'✅ ' if current_rooms == room else ''}{room} комн"
        room_buttons.append(
            InlineKeyboardButton(label, callback_data=f"fset:rooms:{room}"),
        )
    keyboard.append(room_buttons)
    # Clear rooms
    if current_rooms is not None:
        keyboard.append([
            InlineKeyboardButton("❌ Сбросить комнаты", callback_data="fclear:rooms"),
        ])

    # Stepper fields — each gets a row with - value +
    for field in ["price_from", "price_to", "area_from", "area_to", "floor_from", "floor_to"]:
        label = FILTER_FIELDS[field]
        value = _format_field_value(config, field)
        keyboard.append([
            InlineKeyboardButton(f"{label}: {value}", callback_data=f"ffield:{field}"),
        ])

    # Text search
    text_value = _format_field_value(config, "text")
    keyboard.append([
        InlineKeyboardButton(f"📝 Текст: {text_value}", callback_data="ftext"),
    ])

    # Navigation
    keyboard.append([
        InlineKeyboardButton("🔍 Применить фильтр", callback_data="cmd:filter"),
        InlineKeyboardButton("🏠 В меню", callback_data="menu"),
    ])

    return InlineKeyboardMarkup(keyboard)


def build_stepper_keyboard(
    field: str,
    config: SearchConfig,
) -> InlineKeyboardMarkup:
    """Build a +/- stepper keyboard for a numeric field."""
    min_val, max_val, step = STEPPERS[field]
    current = getattr(config, field, None)

    keyboard: list[list[InlineKeyboardButton]] = []

    # Quick presets
    if field in {"price_from", "price_to"}:
        presets = [10_000_000, 20_000_000, 30_000_000, 50_000_000, 80_000_000, 100_000_000]
    elif field in {"area_from", "area_to"}:
        presets = [30.0, 40.0, 50.0, 60.0, 80.0, 100.0]
    else:  # floor
        presets = [1, 2, 3, 5, 10, 15]

    preset_buttons: list[InlineKeyboardButton] = []
    for val in presets:
        if min_val <= val <= max_val:
            label = f"{'✅' if current == val else ''}{int(val) if isinstance(val, int) or val == int(val) else val}"
            preset_buttons.append(
                InlineKeyboardButton(label, callback_data=f"fset:{field}:{val}"),
            )
    # Split presets into rows of 3
    for i in range(0, len(preset_buttons), 3):
        keyboard.append(preset_buttons[i : i + 3])

    # +/- stepper
    stepper_row: list[InlineKeyboardButton] = []
    if current is not None:
        new_minus = current - step
        if new_minus >= min_val:
            stepper_row.append(
                InlineKeyboardButton(f"➖ {int(step) if step == int(step) else step}", callback_data=f"fstep:{field}:{new_minus}"),
            )
    stepper_row.append(InlineKeyboardButton("⬆️ Назад к фильтру", callback_data="fmenu"))
    if current is not None:
        new_plus = current + step
        if new_plus <= max_val:
            stepper_row.append(
                InlineKeyboardButton(f"➕ {int(step) if step == int(step) else step}", callback_data=f"fstep:{field}:{new_plus}"),
            )
    keyboard.append(stepper_row)

    # Clear button
    if current is not None:
        keyboard.append([
            InlineKeyboardButton(f"❌ Сбросить", callback_data=f"fclear:{field}"),
        ])

    keyboard.append([InlineKeyboardButton("🏠 В меню", callback_data="menu")])
    return InlineKeyboardMarkup(keyboard)


async def _get_config(session: AsyncSession) -> SearchConfig:
    """Get the active search config, creating a default if none exists."""
    configs = await get_active_configs(session)
    if configs:
        return configs[0]
    return await get_or_create_default(session)


async def _send_filter_editor(update: Update, session: AsyncSession) -> None:
    """Send or refresh the filter editor view."""
    query = update.callback_query
    config = await _get_config(session)
    text = format_filter_editor_message(config)
    keyboard = build_filter_editor_keyboard(config)

    if query is not None:
        await query.answer()
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=keyboard)
    elif update.effective_message is not None:
        await update.effective_message.reply_text(text, parse_mode="HTML", reply_markup=keyboard)


async def _send_stepper(update: Update, session: AsyncSession, field: str) -> None:
    """Send the +/- stepper view for a specific field."""
    query = update.callback_query
    if query is None:
        return
    config = await _get_config(session)
    text = f"⚙️ <b>{html.escape(FILTER_FIELDS[field])}</b>\n\nТекущее: <b>{_format_field_value(config, field)}</b>\n\nВыберите значение или используйте +/-:"
    keyboard = build_stepper_keyboard(field, config)
    await query.answer()
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=keyboard)


async def _set_field(
    update: Update,
    session: AsyncSession,
    field: str,
    raw_value: str,
) -> None:
    """Set a filter field to a specific value from inline button."""
    query = update.callback_query
    if query is None:
        return

    config = await _get_config(session)

    # Parse the value
    if field == "rooms":
        value: object = int(raw_value)
    elif field in {"price_from", "price_to"}:
        value = int(float(raw_value))
    elif field in {"area_from", "area_to"}:
        value = float(raw_value)
    elif field in {"floor_from", "floor_to"}:
        value = int(float(raw_value))
    else:
        value = raw_value

    # Validate using existing validation
    from app.telegram.settings_validation import validate_field_value

    area_from = config.area_from
    area_to = config.area_to
    validated, error = validate_field_value(
        field,
        str(raw_value),
        area_from=area_from,
        area_to=area_to,
    )
    if error is not None:
        await query.answer(error, show_alert=True)
        return

    await update_field(session, config.id, field, validated)
    await session.commit()

    # Invalidate cache
    from app.telegram.cache import apartment_list_cache

    await apartment_list_cache.clear()

    await query.answer("✅ Сохранено")
    await _send_filter_editor(update, session)


async def _clear_field(update: Update, session: AsyncSession, field: str) -> None:
    """Clear a filter field (set to None)."""
    query = update.callback_query
    if query is None:
        return

    config = await _get_config(session)
    await update_field(session, config.id, field, None)
    await session.commit()

    from app.telegram.cache import apartment_list_cache

    await apartment_list_cache.clear()

    await query.answer("🗑 Сброшено")
    await _send_filter_editor(update, session)


async def _handle_text_input_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Prompt user to send text for the text search field."""
    query = update.callback_query
    if query is None:
        return
    await query.answer()
    await query.message.reply_text(  # type: ignore[union-attr]
        "📝 Введите текст для поиска (или «-» для сброса):",
    )
    # Set state for the text input handler
    if context.user_data is None:
        context.user_data = {}
    context.user_data["filter_text_input"] = True


async def handle_filter_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Handle filter-related callback queries.

    Returns True if the callback was handled, False otherwise.
    """
    query = update.callback_query
    if query is None or query.data is None:
        return False

    data = query.data

    try:
        async with AsyncSessionLocal() as session:
            if FILTER_MENU_PATTERN.match(data):
                await _send_filter_editor(update, session)
                return True

            if FILTER_TEXT_PATTERN.match(data):
                await _handle_text_input_start(update, context)
                return True

            field_match = FILTER_FIELD_PATTERN.match(data)
            if field_match:
                field = field_match.group(1)
                if field in STEPPERS:
                    await _send_stepper(update, session, field)
                    return True

            set_match = FILTER_SET_PATTERN.match(data)
            if set_match:
                field = set_match.group(1)
                value = set_match.group(2)
                await _set_field(update, session, field, value)
                return True

            # Stepper: fstep:<field>:<value>
            if data.startswith("fstep:"):
                parts = data.split(":", 2)
                if len(parts) == 3:
                    field = parts[1]
                    value = parts[2]
                    await _set_field(update, session, field, value)
                    return True

            clear_match = FILTER_CLEAR_PATTERN.match(data)
            if clear_match:
                field = clear_match.group(1)
                await _clear_field(update, session, field)
                return True

    except Exception:
        logger.exception("Error in filter callback data={}", data)
        if query is not None:
            await query.answer("⚠️ Ошибка", show_alert=True)
        return True

    return False
