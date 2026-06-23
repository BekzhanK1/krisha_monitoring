from __future__ import annotations

import time
from datetime import UTC, datetime

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.analyzer.deal_analyzer import Deal, DealAnalyzer
from app.config import get_settings
from app.database import AsyncSessionLocal
from app.repositories.apartment_filter import get_filtered_apartments
from app.repositories.search_config_repo import get_active_configs, get_or_create_default
from app.scraper.filters import SearchFilters
from app.telegram.notifications import is_hunter_candidate, notify_hunter_deals
from app.utils.fixture_data import is_fixture_apartment

_hunter_running = False
_last_hunter_run: dict[str, object] | None = None


def get_hunter_job_status() -> dict[str, object] | None:
    if _last_hunter_run is None:
        return None
    return {
        "last_run": _last_hunter_run["finished_at"],
        "alerts_sent": _last_hunter_run["alerts_sent"],
        "candidates_found": _last_hunter_run["candidates_found"],
        "duration_sec": _last_hunter_run["duration_sec"],
        "status": _last_hunter_run["status"],
    }


async def _get_active_filters(session: AsyncSession) -> SearchFilters:
    configs = await get_active_configs(session)
    if not configs:
        config = await get_or_create_default(session)
        return SearchFilters.from_search_config(config)
    return SearchFilters.from_search_config(configs[0])


async def _find_hunter_candidates(
    session: AsyncSession,
    *,
    interval_minutes: int,
) -> list[Deal]:
    filters = await _get_active_filters(session)
    recent_apartments = await get_filtered_apartments(
        session,
        filters,
        limit=500,
        recent_minutes=interval_minutes,
    )
    if not recent_apartments:
        return []

    recent_ids = {apartment.id for apartment in recent_apartments}
    complex_ids = {apartment.complex_id for apartment in recent_apartments}

    analyzer = DealAnalyzer(session)
    candidates: list[Deal] = []
    seen_apartment_ids: set[int] = set()

    for complex_id in complex_ids:
        for deal in await analyzer.find_deals(complex_id):
            apartment_id = deal.apartment.id
            if apartment_id not in recent_ids or apartment_id in seen_apartment_ids:
                continue
            if is_fixture_apartment(deal.apartment):
                logger.debug(
                    "Skipping hunter candidate fixture apartment_id={}",
                    apartment_id,
                )
                continue
            if not is_hunter_candidate(deal):
                continue
            seen_apartment_ids.add(apartment_id)
            candidates.append(deal)

    return candidates


async def hunter_job() -> None:
    global _hunter_running, _last_hunter_run
    if _hunter_running:
        logger.warning("Hunter job already running, skipping")
        return

    _hunter_running = True
    started = time.monotonic()
    settings = get_settings()
    alerts_sent = 0
    candidates_found = 0

    try:
        async with AsyncSessionLocal() as session:
            candidates = await _find_hunter_candidates(
                session,
                interval_minutes=settings.hunter_interval_minutes,
            )
            candidates_found = len(candidates)

            if (
                candidates
                and settings.telegram_bot_token
                and settings.telegram_chat_id
            ):
                alerts_sent = await notify_hunter_deals(candidates, session)
                await session.commit()

        elapsed = time.monotonic() - started
        logger.info(
            "Hunter job done: {} candidates, {} alerts sent",
            candidates_found,
            alerts_sent,
        )
        _last_hunter_run = {
            "finished_at": datetime.now(UTC).isoformat(),
            "alerts_sent": alerts_sent,
            "candidates_found": candidates_found,
            "duration_sec": round(elapsed, 3),
            "status": "success",
        }
    except Exception:
        elapsed = time.monotonic() - started
        logger.exception("Unhandled exception in hunter job")
        _last_hunter_run = {
            "finished_at": datetime.now(UTC).isoformat(),
            "alerts_sent": 0,
            "candidates_found": 0,
            "duration_sec": round(elapsed, 3),
            "status": "error",
        }
    finally:
        _hunter_running = False
