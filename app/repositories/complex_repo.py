from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ResidentialComplex


async def get_or_create(
    session: AsyncSession,
    name: str,
    district: str = "",
) -> ResidentialComplex:
    result = await session.execute(
        select(ResidentialComplex).where(ResidentialComplex.name == name),
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        return existing

    complex_ = ResidentialComplex(name=name, district=district)
    session.add(complex_)
    await session.flush()
    return complex_


async def get_all(session: AsyncSession) -> list[ResidentialComplex]:
    result = await session.execute(select(ResidentialComplex).order_by(ResidentialComplex.name))
    return list(result.scalars().all())
