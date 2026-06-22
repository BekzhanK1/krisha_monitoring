from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.enums import enum_values


class ApartmentStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    PRICE_CHANGED = "price_changed"


class ApartmentStatusHistory(Base):
    __tablename__ = "apartment_status_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    apartment_id: Mapped[int] = mapped_column(
        ForeignKey("apartments.id", ondelete="CASCADE"),
        index=True,
    )
    status: Mapped[ApartmentStatus] = mapped_column(
        Enum(
            ApartmentStatus,
            name="apartment_status",
            values_callable=enum_values,
        ),
    )
    old_price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    new_price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    apartment: Mapped[Apartment] = relationship(back_populates="status_history")


if TYPE_CHECKING:
    from app.models.apartment import Apartment
