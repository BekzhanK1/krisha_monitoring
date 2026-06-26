"""Inline keyboard builders for the Telegram bot."""
from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from app.telegram.pagination import build_pagination_keyboard


def main_menu_keyboard() -> InlineKeyboardMarkup:
    """Main navigation menu shown on /start."""
    keyboard = [
        [
            InlineKeyboardButton("🔍 По фильтру", callback_data="cmd:filter"),
            InlineKeyboardButton("🆕 Новые 24ч", callback_data="cmd:fnew"),
        ],
        [
            InlineKeyboardButton("📊 Все активные", callback_data="cmd:top"),
            InlineKeyboardButton("📉 Скидки", callback_data="cmd:discount"),
        ],
        [
            InlineKeyboardButton("⭐ VIP объекты", callback_data="cmd:vip"),
            InlineKeyboardButton("🏢 ЖК статистика", callback_data="cmd:zhk"),
        ],
        [
            InlineKeyboardButton("📈 Отчёт по рынку", callback_data="cmd:report"),
            InlineKeyboardButton("⚙️ Настройки", callback_data="cmd:settings"),
        ],
        [
            InlineKeyboardButton("⭐ Избранное", callback_data="cmd:favorites"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def listing_detail_keyboard(
    apartment_id: int,
    *,
    is_favorite: bool = False,
    back_callback: str = "cmd:filter",
) -> InlineKeyboardMarkup:
    """Keyboard for a single listing detail view."""
    fav_label = "💔 Убрать из избранного" if is_favorite else "⭐ В избранное"
    keyboard = [
        [InlineKeyboardButton(fav_label, callback_data=f"fav:{apartment_id}:{int(is_favorite)}")],
        [InlineKeyboardButton("🏠 В меню", callback_data="menu")],
    ]
    return InlineKeyboardMarkup(keyboard)


def listing_list_keyboard(
    *,
    prefix: str,
    apartment_ids: list[int],
    current_page: int,
    total_items: int,
    back_callback: str = "menu",
) -> InlineKeyboardMarkup:
    """Keyboard for a paginated list of listings.

    Each listing gets a button; below them are pagination controls.
    """
    listing_buttons = [
        [InlineKeyboardButton(f"🏠 Объект #{apt_id}", callback_data=f"apt:{apt_id}:{prefix}:{current_page}")]
        for apt_id in apartment_ids
    ]
    return build_pagination_keyboard(
        prefix=prefix,
        current_page=current_page,
        total_items=total_items,
        extra_buttons=listing_buttons,
        back_callback=back_callback,
    )


def back_to_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("🏠 В меню", callback_data="menu")]])


def zhk_list_keyboard(
    complexes: list[tuple[int, str, int]],
    *,
    current_page: int = 1,
    total_items: int | None = None,
) -> InlineKeyboardMarkup:
    """Keyboard listing residential complexes for selection."""
    buttons = [
        [InlineKeyboardButton(f"{name} ({count})", callback_data=f"zhk:{cid}")]
        for cid, name, count in complexes
    ]
    total = total_items if total_items is not None else len(complexes)
    return build_pagination_keyboard(
        prefix="zhk_list",
        current_page=current_page,
        total_items=total,
        extra_buttons=buttons,
        back_callback="menu",
    )
