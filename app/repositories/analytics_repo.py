from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Apartment, ResidentialComplex
from app.models.analytics import MarketAnalytics


async def save_snapshot(session: AsyncSession, data: dict[str, Any]) -> MarketAnalytics:
    snapshot = MarketAnalytics(**data)
    session.add(snapshot)
    await session.flush()
    return snapshot


async def get_latest_by_complex(
    session: AsyncSession,
    complex_id: int,
    rooms: int | None = None,
) -> MarketAnalytics | None:
    stmt = (
        select(MarketAnalytics)
        .where(MarketAnalytics.complex_id == complex_id)
        .order_by(desc(MarketAnalytics.calculated_at))
        .limit(1)
    )
    if rooms is not None:
        stmt = stmt.where(MarketAnalytics.rooms == rooms)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_latest_by_district(
    session: AsyncSession,
    district: str,
    rooms: int | None = None,
) -> MarketAnalytics | None:
    stmt = (
        select(MarketAnalytics)
        .where(
            MarketAnalytics.district == district,
            MarketAnalytics.complex_id.is_(None),
        )
        .order_by(desc(MarketAnalytics.calculated_at))
        .limit(1)
    )
    if rooms is not None:
        stmt = stmt.where(MarketAnalytics.rooms == rooms)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_history(
    session: AsyncSession,
    complex_id: int,
    days: int = 90,
) -> list[MarketAnalytics]:
    cutoff = datetime.now(UTC) - timedelta(days=days)
    result = await session.execute(
        select(MarketAnalytics)
        .where(
            MarketAnalytics.complex_id == complex_id,
            MarketAnalytics.calculated_at >= cutoff,
        )
        .order_by(desc(MarketAnalytics.calculated_at)),
    )
    return list(result.scalars().all())


async def get_top_complexes_by_active_count(
    session: AsyncSession,
    *,
    limit: int = 10,
) -> list[tuple[str, int]]:
    latest_subq = (
        select(
            MarketAnalytics.complex_id,
            func.max(MarketAnalytics.calculated_at).label("max_calc"),
        )
        .where(MarketAnalytics.complex_id.is_not(None))
        .group_by(MarketAnalytics.complex_id)
        .subquery()
    )
    result = await session.execute(
        select(ResidentialComplex.name, MarketAnalytics.active_count)
        .select_from(MarketAnalytics)
        .join(
            latest_subq,
            and_(
                MarketAnalytics.complex_id == latest_subq.c.complex_id,
                MarketAnalytics.calculated_at == latest_subq.c.max_calc,
            ),
        )
        .join(ResidentialComplex, ResidentialComplex.id == MarketAnalytics.complex_id)
        .order_by(desc(MarketAnalytics.active_count), ResidentialComplex.name)
        .limit(limit),
    )
    rows = list(result.all())
    if rows:
        return [(name, active_count) for name, active_count in rows]

    live_result = await session.execute(
        select(ResidentialComplex.name, func.count(Apartment.id).label("active_count"))
        .join(Apartment, Apartment.complex_id == ResidentialComplex.id)
        .where(
            Apartment.is_active.is_(True),
            Apartment.external_id.regexp_match("^[0-9]+$"),
        )
        .group_by(ResidentialComplex.id, ResidentialComplex.name)
        .order_by(desc("active_count"), ResidentialComplex.name)
        .limit(limit),
    )
    return [(name, int(active_count)) for name, active_count in live_result.all()]
