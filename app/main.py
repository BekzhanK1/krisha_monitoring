import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from loguru import logger
from telegram.ext import Application

from app.config import get_settings
from app.logging_config import setup_logging
from app.scheduler.jobs import scrape_job
from app.scheduler.scheduler import get_scheduler


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    setup_logging()
    if os.environ.get("PYTEST_CURRENT_TEST"):
        logger.info("Application started (scheduler and bot disabled under pytest)")
        yield
        return

    settings = get_settings()
    scheduler = get_scheduler()
    from apscheduler.triggers.interval import IntervalTrigger

    scheduler.add_job(
        scrape_job,
        trigger=IntervalTrigger(minutes=settings.parser_interval_minutes),
        id="scrape_all",
        replace_existing=True,
        misfire_grace_time=60,
        coalesce=True,
    )
    scheduler.start()

    tg_app: Application | None = None  # type: ignore[type-arg]
    polling_task: asyncio.Task[object] | None = None
    if settings.telegram_bot_token:
        from app.telegram.bot import create_application

        tg_app = create_application()
        await tg_app.initialize()
        await tg_app.start()
        if tg_app.updater is not None:
            polling_task = asyncio.create_task(tg_app.updater.start_polling())
        logger.info("Telegram bot started")
    else:
        logger.warning("TELEGRAM_BOT_TOKEN not set, skipping bot startup")

    logger.info("Application started")
    yield

    if tg_app is not None:
        if tg_app.updater is not None:
            await tg_app.updater.stop()
        if polling_task is not None:
            polling_task.cancel()
            try:
                await polling_task
            except asyncio.CancelledError:
                pass
        await tg_app.stop()
        await tg_app.shutdown()

    scheduler.shutdown(wait=False)


app = FastAPI(title="Krisha Monitoring", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/scheduler/status")
async def scheduler_status() -> dict[str, object]:
    scheduler = get_scheduler()
    jobs = []
    for job in scheduler.get_jobs():
        next_run = job.next_run_time.isoformat() if job.next_run_time is not None else None
        jobs.append(
            {
                "id": job.id,
                "next_run": next_run,
                "trigger": str(job.trigger),
            },
        )
    return {"running": scheduler.running, "jobs": jobs}
