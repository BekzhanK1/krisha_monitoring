from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.search_config import SearchConfig
from app.models.search_config_complex import SearchConfigComplex


async def list_complexes(
    session: AsyncSession,
    config_id: int,
) -> list[SearchConfigComplex]:
    result = await session.execute(
        select(SearchConfigComplex)
        .where(SearchConfigComplex.search_config_id == config_id)
        .order_by(SearchConfigComplex.id),
    )
    return list(result.scalars().all())


async def add_complex(
    session: AsyncSession,
    config_id: int,
    krisha_complex_id: str,
    *,
    name: str | None = None,
) -> SearchConfigComplex:
    krisha_id = krisha_complex_id.strip()
    if not krisha_id:
        msg = "krisha_complex_id must not be empty"
        raise ValueError(msg)
    if not krisha_id.isdigit():
        msg = "krisha_complex_id must be numeric"
        raise ValueError(msg)

    existing = await session.execute(
        select(SearchConfigComplex).where(
            SearchConfigComplex.search_config_id == config_id,
            SearchConfigComplex.krisha_complex_id == krisha_id,
        ),
    )
    row = existing.scalar_one_or_none()
    if row is not None:
        if name is not None:
            cleaned = name.strip() or None
            if cleaned:
                row.name = cleaned
            await session.flush()
        return row

    row = SearchConfigComplex(
        search_config_id=config_id,
        krisha_complex_id=krisha_id,
        name=name.strip() if name and name.strip() else None,
    )
    session.add(row)
    await session.flush()
    return row


async def remove_complex(
    session: AsyncSession,
    config_id: int,
    krisha_complex_id: str,
) -> bool:
    result = await session.execute(
        select(SearchConfigComplex).where(
            SearchConfigComplex.search_config_id == config_id,
            SearchConfigComplex.krisha_complex_id == krisha_complex_id.strip(),
        ),
    )
    row = result.scalar_one_or_none()
    if row is None:
        return False
    await session.delete(row)
    await session.flush()
    return True


async def get_config_with_complexes(
    session: AsyncSession,
    config_id: int,
) -> SearchConfig | None:
    result = await session.execute(
        select(SearchConfig)
        .options(selectinload(SearchConfig.complexes))
        .where(SearchConfig.id == config_id),
    )
    return result.scalar_one_or_none()
