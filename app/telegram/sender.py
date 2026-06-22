from __future__ import annotations

import asyncio

from loguru import logger
from telegram import Bot
from telegram.error import Forbidden, TelegramError

from app.config import get_settings

_RETRY_DELAYS_SEC = (2, 4, 8)


async def send_alert(text: str, chat_id: int | None = None) -> bool:
    """Send an HTML message. Returns True on success."""
    settings = get_settings()
    target_chat = chat_id if chat_id is not None else settings.telegram_chat_id
    if not settings.telegram_bot_token or not target_chat:
        logger.warning("Telegram not configured, skipping message send")
        return False

    bot = Bot(token=settings.telegram_bot_token)
    last_error: Exception | None = None

    for attempt in range(len(_RETRY_DELAYS_SEC) + 1):
        try:
            await bot.send_message(
                chat_id=target_chat,
                text=text,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
            logger.info("Telegram message sent to chat_id={}", target_chat)
            return True
        except Forbidden:
            logger.warning("Telegram bot blocked by user chat_id={}", target_chat)
            return False
        except TelegramError as exc:
            last_error = exc
            if attempt < len(_RETRY_DELAYS_SEC):
                delay = _RETRY_DELAYS_SEC[attempt]
                logger.warning(
                    "Telegram send failed (attempt {}), retrying in {}s: {}",
                    attempt + 1,
                    delay,
                    exc,
                )
                await asyncio.sleep(delay)
            else:
                logger.error("Telegram send failed after retries: {}", exc)

    if last_error is not None:
        logger.error("Telegram send ultimately failed: {}", last_error)
    return False
