from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler(timezone="Asia/Almaty")


def get_scheduler() -> AsyncIOScheduler:
    return scheduler
