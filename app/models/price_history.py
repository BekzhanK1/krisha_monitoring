from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Integer, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ApartmentPrice(Base):
    __tablename__ = "apartment_prices"

    id: Mapped[int] = mapped_column(primary_key=True)
    apartment_id: Mapped[int] = mapped_column(
        ForeignKey("apartments.id", ondelete="CASCADE"),
        index=True,
    )
    price: Mapped[int] = mapped_column(Integer)
    price_per_sqm: Mapped[float] = mapped_column(Float)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    apartment: Mapped[Apartment] = relationship(back_populates="prices")


if TYPE_CHECKING:
    from app.models.apartment import Apartment
