from __future__ import annotations

import asyncio
import os
import time
from datetime import UTC, datetime

from loguru import logger

from app.analyzer.deal_analyzer import DealAnalyzer
from app.analyzer.market_analytics import MarketAnalyticsService
from app.analyzer.scoring_service import score_all_active
from app.config import get_settings
from app.database import AsyncSessionLocal
from app.scraper.scrape_service import ScrapeService
from app.telegram.notifications import notify_new_deals

_is_running = False
_analytics_running = False
_scoring_running = False
_last_analytics_run: dict[str, object] | None = None
_last_scoring_run: dict[str, object] | None = None


def get_analytics_job_status() -> dict[str, object] | None:
    if _last_analytics_run is None:
        return None
    return {
        "last_run": _last_analytics_run["finished_at"],
        "complex_snapshots": _last_analytics_run["complex_snapshots"],
        "district_snapshots": _last_analytics_run["district_snapshots"],
        "duration_sec": _last_analytics_run["duration_sec"],
        "status": _last_analytics_run["status"],
    }


def get_scoring_job_status() -> dict[str, object] | None:
    if _last_scoring_run is None:
        return None
    return {
        "last_run": _last_scoring_run["finished_at"],
        "apartments_scored": _last_scoring_run["apartments_scored"],
        "duration_sec": _last_scoring_run["duration_sec"],
        "status": _last_scoring_run["status"],
    }


async def analytics_job() -> None:
    global _analytics_running, _last_analytics_run
    if _analytics_running:
        logger.warning("Analytics job already running, skipping")
        return

    _analytics_running = True
    started = time.monotonic()
    success = False
    try:
        async with AsyncSessionLocal() as session:
            service = MarketAnalyticsService(session)
            complex_snapshots = await service.compute_and_save_all_complexes()
            district_snapshots = await service.compute_and_save_districts()
            await session.commit()

        elapsed = time.monotonic() - started
        logger.info(
            "Analytics job done: {} complex snapshots, {} district snapshots",
            complex_snapshots,
            district_snapshots,
        )
        _last_analytics_run = {
            "finished_at": datetime.now(UTC).isoformat(),
            "complex_snapshots": complex_snapshots,
            "district_snapshots": district_snapshots,
            "duration_sec": round(elapsed, 3),
            "status": "success",
        }
        success = True
    except Exception:
        elapsed = time.monotonic() - started
        logger.exception("Unhandled exception in analytics job")
        _last_analytics_run = {
            "finished_at": datetime.now(UTC).isoformat(),
            "complex_snapshots": 0,
            "district_snapshots": 0,
            "duration_sec": round(elapsed, 3),
            "status": "error",
        }
    finally:
        _analytics_running = False
        if (
            success
            and get_settings().run_scoring_after_analytics
            and not os.environ.get("PYTEST_CURRENT_TEST")
        ):
            asyncio.create_task(_run_scoring_after_analytics())


async def _run_scoring_after_analytics() -> None:
    try:
        await scoring_job()
    except Exception:
        logger.exception("Scoring job failed after analytics")


async def scoring_job() -> None:
    global _scoring_running, _last_scoring_run
    if _scoring_running:
        logger.warning("Scoring job already running, skipping")
        return

    _scoring_running = True
    started = time.monotonic()
    try:
        async with AsyncSessionLocal() as session:
            apartments_scored = await score_all_active(session)
            await session.commit()

        elapsed = time.monotonic() - started
        logger.info("Scoring job done: {} apartments scored", apartments_scored)
        _last_scoring_run = {
            "finished_at": datetime.now(UTC).isoformat(),
            "apartments_scored": apartments_scored,
            "duration_sec": round(elapsed, 3),
            "status": "success",
        }
    except Exception:
        elapsed = time.monotonic() - started
        logger.exception("Unhandled exception in scoring job")
        _last_scoring_run = {
            "finished_at": datetime.now(UTC).isoformat(),
            "apartments_scored": 0,
            "duration_sec": round(elapsed, 3),
            "status": "error",
        }
    finally:
        _scoring_running = False


async def _run_analytics_after_scrape() -> None:
    try:
        await analytics_job()
    except Exception:
        logger.exception("Analytics job failed after scrape")


async def scrape_job() -> None:
    global _is_running
    if _is_running:
        logger.warning("Scrape job already running, skipping")
        return

    _is_running = True
    started = time.monotonic()
    success = False
    try:
        async with AsyncSessionLocal() as session:
            service = ScrapeService(session)
            results = await service.scrape_all()

            settings = get_settings()
            if settings.telegram_bot_token and settings.telegram_chat_id:
                analyzer = DealAnalyzer(session)
                deals = await analyzer.analyze_all_complexes()
                sent = await notify_new_deals(deals, session)
                await session.commit()
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
        success = True
    except Exception:
        logger.exception("Unhandled exception in scrape job")
    finally:
        elapsed = time.monotonic() - started
        logger.bind(job="scrape_all", duration_sec=elapsed).info("Scrape job finished")
        if success and get_settings().run_analytics_after_scrape:
            asyncio.create_task(_run_analytics_after_scrape())
        _is_running = False
