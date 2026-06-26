from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.apartment import Apartment
from app.models.telegram import Favorite, TelegramUser


async def get_or_create_user(
    session: AsyncSession,
    *,
    telegram_id: int,
    username: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
) -> TelegramUser:
    """Get an existing TelegramUser by telegram_id, or create a new one."""
    result = await session.execute(
        select(TelegramUser).where(TelegramUser.telegram_id == str(telegram_id)),
    )
    user = result.scalar_one_or_none()
    if user is not None:
        user.username = username or user.username
        user.first_name = first_name or user.first_name
        user.last_name = last_name or user.last_name
        user.last_seen_at = datetime.now(UTC)
        await session.flush()
        return user

    user = TelegramUser(
        telegram_id=str(telegram_id),
        username=username,
        first_name=first_name,
        last_name=last_name,
    )
    session.add(user)
    await session.flush()
    return user


async def add_favorite(session: AsyncSession, user_id: int, apartment_id: int) -> bool:
    """Add a favorite. Returns True if newly created, False if already existed."""
    existing = await session.execute(
        select(Favorite.id).where(
            Favorite.user_id == user_id,
            Favorite.apartment_id == apartment_id,
        ),
    )
    if existing.scalar_one_or_none() is not None:
        return False

    fav = Favorite(user_id=user_id, apartment_id=apartment_id)
    session.add(fav)
    await session.flush()
    return True


async def remove_favorite(session: AsyncSession, user_id: int, apartment_id: int) -> bool:
    """Remove a favorite. Returns True if removed, False if not found."""
    result = await session.execute(
        delete(Favorite).where(
            Favorite.user_id == user_id,
            Favorite.apartment_id == apartment_id,
        ),
    )
    return result.rowcount > 0


async def is_favorite(session: AsyncSession, user_id: int, apartment_id: int) -> bool:
    result = await session.execute(
        select(Favorite.id).where(
            Favorite.user_id == user_id,
            Favorite.apartment_id == apartment_id,
        ),
    )
    return result.scalar_one_or_none() is not None


async def get_favorite_apartments(
    session: AsyncSession,
    user_id: int,
    *,
    limit: int = 10,
    offset: int = 0,
) -> list[Apartment]:
    """Get favorited apartments for a user, with pagination."""
    result = await session.execute(
        select(Apartment)
        .join(Favorite, Favorite.apartment_id == Apartment.id)
        .options(joinedload(Apartment.complex))
        .where(Favorite.user_id == user_id)
        .order_by(Favorite.created_at.desc())
        .limit(limit)
        .offset(offset),
    )
    return list(result.scalars().unique().all())


async def count_favorites(session: AsyncSession, user_id: int) -> int:
    from sqlalchemy import func

    result = await session.execute(
        select(func.count()).select_from(Favorite).where(Favorite.user_id == user_id),
    )
    return int(result.scalar_one())
