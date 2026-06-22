from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models import Apartment
from app.scraper.filters import SearchFilters
from app.scraper.urls import is_valid_listing_id


def apply_search_filters(
    stmt: Select[tuple[Apartment]],
    filters: SearchFilters,
) -> Select[tuple[Apartment]]:
    if filters.rooms is not None:
        stmt = stmt.where(Apartment.rooms == filters.rooms)
    if filters.price_from is not None:
        stmt = stmt.where(Apartment.price >= filters.price_from)
    if filters.price_to is not None:
        stmt = stmt.where(Apartment.price <= filters.price_to)
    if filters.floor_from is not None:
        stmt = stmt.where(Apartment.floor >= filters.floor_from)
    if filters.floor_to is not None:
        stmt = stmt.where(Apartment.floor <= filters.floor_to)
    if filters.building_floors_from is not None:
        stmt = stmt.where(Apartment.total_floors >= filters.building_floors_from)
    if filters.building_floors_to is not None:
        stmt = stmt.where(Apartment.total_floors <= filters.building_floors_to)
    if filters.year_from is not None:
        stmt = stmt.where(Apartment.year_built >= filters.year_from)
    if filters.year_to is not None:
        stmt = stmt.where(Apartment.year_built <= filters.year_to)
    if filters.area_from is not None:
        stmt = stmt.where(Apartment.total_area >= filters.area_from)
    if filters.area_to is not None:
        stmt = stmt.where(Apartment.total_area <= filters.area_to)
    if filters.text:
        stmt = stmt.where(Apartment.description.ilike(f"%{filters.text}%"))
    return stmt


async def get_filtered_apartments(
    session: AsyncSession,
    filters: SearchFilters,
    *,
    limit: int = 10,
    recent_hours: int | None = None,
) -> list[Apartment]:
    stmt = (
        select(Apartment)
        .options(joinedload(Apartment.complex))
        .where(
            Apartment.is_active.is_(True),
            Apartment.external_id.regexp_match("^[0-9]+$"),
        )
    )
    stmt = apply_search_filters(stmt, filters)
    if recent_hours is not None:
        cutoff = datetime.now(UTC) - timedelta(hours=recent_hours)
        stmt = stmt.where(Apartment.first_seen_at > cutoff).order_by(
            Apartment.first_seen_at.desc(),
        )
    else:
        stmt = stmt.order_by(Apartment.price_per_sqm.asc())
    stmt = stmt.limit(limit)
    result = await session.execute(stmt)
    return [apt for apt in result.scalars().unique().all() if is_valid_listing_id(apt.external_id)]
