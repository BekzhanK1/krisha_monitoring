from __future__ import annotations

from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters

from app.config import get_settings
from app.telegram.callbacks import handle_callback
from app.telegram.handlers import (
    cmd_discount,
    cmd_filter,
    cmd_fnew,
    cmd_favorites,
    cmd_menu,
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
    application.add_handler(CommandHandler("menu", cmd_menu))
    application.add_handler(CommandHandler("filter", cmd_filter))
    application.add_handler(CommandHandler("fnew", cmd_fnew))
    application.add_handler(CommandHandler("top", cmd_top))
    application.add_handler(CommandHandler("new", cmd_new))
    application.add_handler(CommandHandler("discount", cmd_discount))
    application.add_handler(CommandHandler("zhk", cmd_zhk))
    application.add_handler(CommandHandler("report", cmd_report))
    application.add_handler(CommandHandler("vip", cmd_vip))
    application.add_handler(CommandHandler("favorites", cmd_favorites))
    application.add_handler(CommandHandler("settings", cmd_settings))

    # Settings inline keyboard editing (fields + complex list)
    application.add_handler(
        CallbackQueryHandler(callback_settings_edit, pattern=r"^(edit:\d+:|cdel:\d+:)"),
    )

    # Main callback router for inline navigation (menu, listings, favorites, etc.)
    # This handler catches all other callback queries not matched by settings.
    application.add_handler(CallbackQueryHandler(handle_callback))

    # Free-text input for settings editing
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
