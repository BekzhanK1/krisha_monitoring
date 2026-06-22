from __future__ import annotations

import time

from loguru import logger

from app.analyzer.deal_analyzer import DealAnalyzer
from app.config import get_settings
from app.database import AsyncSessionLocal
from app.scraper.scrape_service import ScrapeService
from app.telegram.notifications import notify_new_deals

_is_running = False


async def scrape_job() -> None:
    global _is_running
    if _is_running:
        logger.warning("Scrape job already running, skipping")
        return

    _is_running = True
    started = time.monotonic()
    try:
        async with AsyncSessionLocal() as session:
            service = ScrapeService(session)
            results = await service.scrape_all()

            settings = get_settings()
            if settings.telegram_bot_token and settings.telegram_chat_id:
                analyzer = DealAnalyzer(session)
                deals = await analyzer.analyze_all_complexes()
                sent = await notify_new_deals(deals, session)
                logger.info("Sent {} deal notifications", sent)

        for result in results:
            logger.bind(
                job="scrape_all",
                label=result.label,
                total_found=result.total_found,
                new=result.new,
                updated=result.updated,
                unchanged=result.unchanged,
                skipped_recent=result.skipped_recent,
                errors=result.errors,
                marked_inactive=result.marked_inactive,
                duration_sec=result.duration_sec,
            ).info("Scrape job result")
    except Exception:
        logger.exception("Unhandled exception in scrape job")
    finally:
        elapsed = time.monotonic() - started
        logger.bind(job="scrape_all", duration_sec=elapsed).info("Scrape job finished")
        _is_running = False
