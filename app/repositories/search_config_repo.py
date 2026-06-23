from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.search_config import SearchConfig

DEFAULT_CONFIG_NAME = "default"

EDITABLE_FIELDS = frozenset(
    {"price_to", "rooms", "area_from", "area_to", "text"},
)


async def get_active_configs(session: AsyncSession) -> list[SearchConfig]:
    result = await session.execute(
        select(SearchConfig).where(SearchConfig.is_active.is_(True)).order_by(SearchConfig.id),
    )
    return list(result.scalars().all())


async def get_by_name(session: AsyncSession, name: str) -> SearchConfig | None:
    result = await session.execute(
        select(SearchConfig).where(SearchConfig.name == name),
    )
    return result.scalar_one_or_none()


async def get_or_create_default(session: AsyncSession) -> SearchConfig:
    existing = await get_by_name(session, DEFAULT_CONFIG_NAME)
    if existing is not None:
        existing.city = "astana"
        existing.is_active = True
        existing.rooms = None
        existing.price_from = None
        existing.price_to = None
        existing.floor_from = None
        existing.floor_to = None
        existing.building_floors_from = None
        existing.building_floors_to = None
        existing.year_from = None
        existing.year_to = None
        existing.area_from = None
        existing.area_to = None
        existing.text = None
        existing.complex_id = None
        await session.flush()
        return existing

    config = SearchConfig(name=DEFAULT_CONFIG_NAME, city="astana")
    session.add(config)
    await session.flush()
    return config


async def update_config(
    session: AsyncSession,
    name: str,
    data: dict[str, Any],
) -> SearchConfig:
    config = await get_by_name(session, name)
    if config is None:
        config = SearchConfig(name=name, city=data.get("city", "astana"))
        session.add(config)

    allowed_fields = {
        "is_active",
        "city",
        "rooms",
        "price_from",
        "price_to",
        "floor_from",
        "floor_to",
        "building_floors_from",
        "building_floors_to",
        "year_from",
        "year_to",
        "area_from",
        "area_to",
        "text",
        "complex_id",
    }
    for field, value in data.items():
        if field not in allowed_fields:
            continue
        if field == "text" and isinstance(value, str):
            value = value.strip() or None
        setattr(config, field, value)

    await session.flush()
    return config


async def update_field(
    session: AsyncSession,
    config_id: int,
    field: str,
    value: Any,
) -> SearchConfig:
    if field not in EDITABLE_FIELDS:
        msg = f"Field {field!r} is not editable"
        raise ValueError(msg)

    result = await session.execute(
        select(SearchConfig).where(SearchConfig.id == config_id),
    )
    config = result.scalar_one_or_none()
    if config is None:
        msg = f"SearchConfig id={config_id} not found"
        raise ValueError(msg)

    if field == "text" and isinstance(value, str):
        value = value.strip() or None

    setattr(config, field, value)
    await session.flush()
    return config
