from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import get_settings


@pytest.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    """Session wrapped in outer transaction — all commits roll back after test."""
    get_settings.cache_clear()
    engine = create_async_engine(
        get_settings().database_url,
        poolclass=NullPool,
    )
    async with engine.connect() as connection:
        async with connection.begin() as transaction:
            session = AsyncSession(bind=connection, expire_on_commit=False)
            yield session
            await session.close()
            await transaction.rollback()
    await engine.dispose()
