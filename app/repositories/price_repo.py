from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ApartmentPrice


async def record_price_change(
    session: AsyncSession,
    apartment_id: int,
    price: int,
    price_per_sqm: float,
) -> ApartmentPrice:
    entry = ApartmentPrice(
        apartment_id=apartment_id,
        price=price,
        price_per_sqm=price_per_sqm,
    )
    session.add(entry)
    await session.flush()
    return entry


async def get_price_history(
    session: AsyncSession,
    apartment_id: int,
) -> list[ApartmentPrice]:
    result = await session.execute(
        select(ApartmentPrice)
        .where(ApartmentPrice.apartment_id == apartment_id)
        .order_by(ApartmentPrice.recorded_at),
    )
    return list(result.scalars().all())
