from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, Float, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.enums import enum_values


class SellerType(StrEnum):
    OWNER = "owner"
    AGENT = "agent"
    AGENCY = "agency"


class Seller(Base):
    __tablename__ = "sellers"

    id: Mapped[int] = mapped_column(primary_key=True)
    apartment_id: Mapped[int] = mapped_column(
        ForeignKey("apartments.id", ondelete="CASCADE"),
        index=True,
    )
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    seller_type: Mapped[SellerType | None] = mapped_column(
        Enum(
            SellerType,
            name="seller_type",
            values_callable=enum_values,
        ),
        nullable=True,
    )
    owner_probability: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    apartment: Mapped[Apartment] = relationship(back_populates="sellers")


if TYPE_CHECKING:
    from app.models.apartment import Apartment
