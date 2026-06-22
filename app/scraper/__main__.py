from __future__ import annotations

import asyncio

from loguru import logger

from app.database import AsyncSessionLocal
from app.logging_config import setup_logging
from app.scraper.scrape_service import ScrapeService


async def main() -> None:
    setup_logging()
    logger.info("Starting manual scrape cycle")

    async with AsyncSessionLocal() as session:
        service = ScrapeService(session)
        results = await service.scrape_all()

    for result in results:
        logger.info(
            "Result {}: found={} new={} updated={} unchanged={} skipped={} errors={} inactive={}",
            result.label,
            result.total_found,
            result.new,
            result.updated,
            result.unchanged,
            result.skipped_recent,
            result.errors,
            result.marked_inactive,
        )


if __name__ == "__main__":
    asyncio.run(main())
