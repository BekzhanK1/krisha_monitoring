"""Pagination utilities for Telegram inline keyboards.

Callback data format: ``<prefix>:<page>`` where page is 1-based.
"""
from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

ITEMS_PER_PAGE = 5


def build_pagination_keyboard(
    *,
    prefix: str,
    current_page: int,
    total_items: int,
    per_page: int = ITEMS_PER_PAGE,
    extra_buttons: list[list[InlineKeyboardButton]] | None = None,
    back_callback: str | None = None,
) -> InlineKeyboardMarkup:
    """Build a pagination keyboard with prev/next and optional back button."""
    total_pages = max(1, (total_items + per_page - 1) // per_page)
    nav_row: list[InlineKeyboardButton] = []

    if current_page > 1:
        nav_row.append(
            InlineKeyboardButton("⬅️ Назад", callback_data=f"{prefix}:{current_page - 1}"),
        )

    nav_row.append(
        InlineKeyboardButton(f"{current_page}/{total_pages}", callback_data="noop"),
    )

    if current_page < total_pages:
        nav_row.append(
            InlineKeyboardButton("Вперёд ➡️", callback_data=f"{prefix}:{current_page + 1}"),
        )

    keyboard: list[list[InlineKeyboardButton]] = []
    if extra_buttons:
        keyboard.extend(extra_buttons)
    keyboard.append(nav_row)

    if back_callback:
        keyboard.append([InlineKeyboardButton("🏠 В меню", callback_data=back_callback)])

    return InlineKeyboardMarkup(keyboard)


def paginate_items[T](
    items: list[T],
    page: int,
    per_page: int = ITEMS_PER_PAGE,
) -> tuple[list[T], int]:
    """Return a slice of items for the given page and the effective page number."""
    if not items:
        return [], 1
    total_pages = max(1, (len(items) + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))
    start = (page - 1) * per_page
    end = start + per_page
    return items[start:end], page
