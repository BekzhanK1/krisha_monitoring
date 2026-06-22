import sys
from pathlib import Path

from loguru import logger

from app.config import get_settings

LOG_FORMAT = "{time:YYYY-MM-DD HH:mm:ss} | {level} | {name}:{line} | {message}"


def setup_logging() -> None:
    settings = get_settings()
    logger.remove()

    logger.add(
        sys.stdout,
        level=settings.log_level,
        format=LOG_FORMAT,
        colorize=True,
    )

    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    logger.add(
        "logs/app.log",
        level=settings.log_level,
        format=LOG_FORMAT,
        rotation="10 MB",
        retention="7 days",
        compression="zip",
    )
