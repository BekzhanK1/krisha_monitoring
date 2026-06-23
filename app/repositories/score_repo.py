from __future__ import annotations

from typing import Any

from sqlalchemy import Case, case, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models import Apartment
from app.models.apartment_score import ApartmentScore
from app.repositories.apartment_filter import apply_search_filters
from app.scraper.filters import SearchFilters
from app.scraper.urls import is_valid_listing_id


async def get_by_apartment_id(
    session: AsyncSession,
    apartment_id: int,
) -> ApartmentScore | None:
    result = await session.execute(
        select(ApartmentScore).where(ApartmentScore.apartment_id == apartment_id),
    )
    return result.scalar_one_or_none()


async def upsert_score(
    session: AsyncSession,
    apartment_id: int,
    data: dict[str, Any],
) -> ApartmentScore:
    existing = await get_by_apartment_id(session, apartment_id)
    if existing is not None:
        for key, value in data.items():
            setattr(existing, key, value)
        await session.flush()
        return existing

    score = ApartmentScore(apartment_id=apartment_id, **data)
    session.add(score)
    await session.flush()
    return score


async def get_top_grades(
    session: AsyncSession,
    grades: list[str],
    limit: int = 10,
) -> list[ApartmentScore]:
    result = await session.execute(
        select(ApartmentScore)
        .where(ApartmentScore.grade.in_(grades))
        .order_by(desc(ApartmentScore.score))
        .limit(limit),
    )
    return list(result.scalars().all())


def _grade_order_case() -> Case[int]:
    return case(
        (ApartmentScore.grade == "A+", 0),
        (ApartmentScore.grade == "A", 1),
        (ApartmentScore.grade == "B", 2),
        (ApartmentScore.grade == "C", 3),
        else_=4,
    )


async def has_scores(session: AsyncSession) -> bool:
    result = await session.execute(select(func.count()).select_from(ApartmentScore))
    return int(result.scalar_one()) > 0


async def get_vip_apartments(
    session: AsyncSession,
    filters: SearchFilters,
    *,
    limit: int = 5,
) -> list[tuple[Apartment, ApartmentScore]]:
    stmt = (
        select(Apartment, ApartmentScore)
        .join(ApartmentScore, ApartmentScore.apartment_id == Apartment.id)
        .options(joinedload(Apartment.complex))
        .where(
            Apartment.is_active.is_(True),
            Apartment.external_id.regexp_match("^[0-9]+$"),
            ApartmentScore.grade.in_(("A+", "A")),
        )
    )
    stmt = apply_search_filters(stmt, filters)
    stmt = stmt.order_by(
        _grade_order_case(),
        desc(ApartmentScore.score),
        desc(ApartmentScore.discount_pct),
    ).limit(limit)
    result = await session.execute(stmt)
    pairs: list[tuple[Apartment, ApartmentScore]] = []
    for apartment, score in result.unique().all():
        if is_valid_listing_id(apartment.external_id):
            pairs.append((apartment, score))
    return pairs


async def get_top_by_grade(
    session: AsyncSession,
    *,
    limit: int = 3,
) -> list[ApartmentScore]:
    result = await session.execute(
        select(ApartmentScore)
        .join(Apartment, Apartment.id == ApartmentScore.apartment_id)
        .options(joinedload(ApartmentScore.apartment).joinedload(Apartment.complex))
        .where(
            Apartment.is_active.is_(True),
            Apartment.external_id.regexp_match("^[0-9]+$"),
        )
        .order_by(_grade_order_case(), desc(ApartmentScore.score))
        .limit(limit),
    )
    return list(result.scalars().unique().all())
