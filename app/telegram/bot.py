from __future__ import annotations

from telegram.ext import Application, CommandHandler

from app.config import get_settings
from app.telegram.handlers import (
    cmd_discount,
    cmd_filter,
    cmd_fnew,
    cmd_new,
    cmd_settings,
    cmd_start,
    cmd_top,
)


def register_handlers(application: Application) -> None:  # type: ignore[type-arg]
    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("filter", cmd_filter))
    application.add_handler(CommandHandler("fnew", cmd_fnew))
    application.add_handler(CommandHandler("top", cmd_top))
    application.add_handler(CommandHandler("new", cmd_new))
    application.add_handler(CommandHandler("discount", cmd_discount))
    application.add_handler(CommandHandler("settings", cmd_settings))


def create_application() -> Application:  # type: ignore[type-arg]
    settings = get_settings()
    application = Application.builder().token(settings.telegram_bot_token).build()
    register_handlers(application)
    return application
