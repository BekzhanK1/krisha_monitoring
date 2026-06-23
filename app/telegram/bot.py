from __future__ import annotations

from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters

from app.config import get_settings
from app.telegram.handlers import (
    cmd_discount,
    cmd_filter,
    cmd_fnew,
    cmd_new,
    cmd_report,
    cmd_settings,
    cmd_start,
    cmd_top,
    cmd_vip,
    cmd_zhk,
)
from app.telegram.settings_handlers import (
    callback_settings_edit,
    handle_settings_input,
)


def register_handlers(application: Application) -> None:  # type: ignore[type-arg]
    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("filter", cmd_filter))
    application.add_handler(CommandHandler("fnew", cmd_fnew))
    application.add_handler(CommandHandler("top", cmd_top))
    application.add_handler(CommandHandler("new", cmd_new))
    application.add_handler(CommandHandler("discount", cmd_discount))
    application.add_handler(CommandHandler("zhk", cmd_zhk))
    application.add_handler(CommandHandler("report", cmd_report))
    application.add_handler(CommandHandler("vip", cmd_vip))
    application.add_handler(CommandHandler("settings", cmd_settings))

    application.add_handler(CallbackQueryHandler(callback_settings_edit, pattern=r"^edit:\d+:"))
    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_settings_input,
            block=False,
        ),
    )


def create_application() -> Application:  # type: ignore[type-arg]
    settings = get_settings()
    application = Application.builder().token(settings.telegram_bot_token).build()
    register_handlers(application)
    return application
