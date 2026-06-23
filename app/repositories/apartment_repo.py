from datetime import UTC, datetime, timedelta
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Apartment, ApartmentStatus, ApartmentStatusHistory
from app.repositories.price_repo import record_price_change


async def get_by_external_id(session: AsyncSession, external_id: str) -> Apartment | None:
    result = await session.execute(
        select(Apartment).where(Apartment.external_id == external_id),
    )
    return result.scalar_one_or_none()


async def get_all_active(
    session: AsyncSession,
    *,
    valid_external_id_only: bool = True,
) -> list[Apartment]:
    stmt = select(Apartment).where(Apartment.is_active.is_(True))
    if valid_external_id_only:
        stmt = stmt.where(Apartment.external_id.regexp_match("^[0-9]+$"))
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_active_by_complex(
    session: AsyncSession,
    complex_id: int,
    *,
    rooms: int | None = None,
    valid_external_id_only: bool = False,
) -> list[Apartment]:
    conditions = [
        Apartment.complex_id == complex_id,
        Apartment.is_active.is_(True),
    ]
    if valid_external_id_only:
        conditions.append(Apartment.external_id.regexp_match("^[0-9]+$"))
    if rooms is not None:
        conditions.append(Apartment.rooms == rooms)
    result = await session.execute(select(Apartment).where(*conditions))
    return list(result.scalars().all())


async def get_inactive_by_complex(
    session: AsyncSession,
    complex_id: int,
    *,
    rooms: int | None = None,
    valid_external_id_only: bool = True,
) -> list[Apartment]:
    conditions = [
        Apartment.complex_id == complex_id,
        Apartment.is_active.is_(False),
    ]
    if valid_external_id_only:
        conditions.append(Apartment.external_id.regexp_match("^[0-9]+$"))
    if rooms is not None:
        conditions.append(Apartment.rooms == rooms)
    result = await session.execute(select(Apartment).where(*conditions))
    return list(result.scalars().all())


async def get_inactive_by_district(
    session: AsyncSession,
    district: str,
    *,
    rooms: int | None = None,
) -> list[Apartment]:
    conditions = [
        Apartment.district == district,
        Apartment.is_active.is_(False),
        Apartment.external_id.regexp_match("^[0-9]+$"),
    ]
    if rooms is not None:
        conditions.append(Apartment.rooms == rooms)
    result = await session.execute(select(Apartment).where(*conditions))
    return list(result.scalars().all())


async def get_active_by_district(
    session: AsyncSession,
    district: str,
    *,
    rooms: int | None = None,
) -> list[Apartment]:
    conditions = [
        Apartment.district == district,
        Apartment.is_active.is_(True),
        Apartment.external_id.regexp_match("^[0-9]+$"),
    ]
    if rooms is not None:
        conditions.append(Apartment.rooms == rooms)
    result = await session.execute(select(Apartment).where(*conditions))
    return list(result.scalars().all())


async def get_distinct_active_districts(session: AsyncSession) -> list[str]:
    result = await session.execute(
        select(Apartment.district)
        .where(
            Apartment.is_active.is_(True),
            Apartment.external_id.regexp_match("^[0-9]+$"),
            Apartment.district != "",
        )
        .distinct()
        .order_by(Apartment.district),
    )
    return list(result.scalars().all())


async def upsert_apartment(
    session: AsyncSession,
    data: dict[str, Any],
) -> tuple[Apartment, bool, bool]:
    external_id = data["external_id"]
    existing = await get_by_external_id(session, external_id)
    now = datetime.now(UTC)

    if existing is None:
        apartment = Apartment(
            external_id=external_id,
            url=data["url"],
            complex_id=data["complex_id"],
            price=data["price"],
            price_per_sqm=data["price_per_sqm"],
            district=data.get("district", ""),
            address=data.get("address", ""),
            rooms=data["rooms"],
            total_area=data["total_area"],
            living_area=data.get("living_area"),
            kitchen_area=data.get("kitchen_area"),
            floor=data.get("floor"),
            total_floors=data.get("total_floors"),
            year_built=data.get("year_built"),
            house_type=data.get("house_type"),
            ceiling_height=data.get("ceiling_height"),
            condition=data.get("condition"),
            balcony=data.get("balcony"),
            bathroom=data.get("bathroom"),
            description=data.get("description"),
            photos=data.get("photos"),
            seller_type=data.get("seller_type"),
            is_active=True,
            first_seen_at=now,
            last_seen_at=now,
        )
        session.add(apartment)
        await session.flush()

        session.add(
            ApartmentStatusHistory(
                apartment_id=apartment.id,
                status=ApartmentStatus.ACTIVE,
                new_price=apartment.price,
            ),
        )
        await record_price_change(
            session,
            apartment.id,
            apartment.price,
            apartment.price_per_sqm,
        )
        return apartment, True, False

    old_price = existing.price
    price_changed = old_price != data["price"]
    existing.price = data["price"]
    existing.price_per_sqm = data["price_per_sqm"]
    existing.last_seen_at = now
    existing.is_active = True

    if price_changed:
        await record_price_change(
            session,
            existing.id,
            data["price"],
            data["price_per_sqm"],
        )
        session.add(
            ApartmentStatusHistory(
                apartment_id=existing.id,
                status=ApartmentStatus.PRICE_CHANGED,
                old_price=old_price,
                new_price=data["price"],
            ),
        )

    await session.flush()
    return existing, False, price_changed


async def mark_inactive(
    session: AsyncSession,
    external_ids_to_keep: list[str],
    complex_id: int,
    *,
    parser_interval_minutes: int,
    complex_name: str = "",
) -> list[Apartment]:
    cutoff = datetime.now(UTC) - timedelta(minutes=2 * parser_interval_minutes)
    keep_ids = external_ids_to_keep or [""]

    result = await session.execute(
        select(Apartment).where(
            Apartment.complex_id == complex_id,
            Apartment.is_active.is_(True),
            Apartment.external_id.not_in(keep_ids),
            Apartment.last_seen_at < cutoff,
        ),
    )
    marked = list(result.scalars().all())

    for apartment in marked:
        apartment.is_active = False
        session.add(
            ApartmentStatusHistory(
                apartment_id=apartment.id,
                status=ApartmentStatus.INACTIVE,
                old_price=apartment.price,
            ),
        )

    await session.flush()
    label = complex_name or str(complex_id)
    logger.info("Marked {} apartments as inactive in {}", len(marked), label)
    # TODO (Epic 5): send Telegram notifications for watchlist apartments in `marked`
    return marked
