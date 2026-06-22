from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Apartment(Base):
    __tablename__ = "apartments"
    __table_args__ = (
        Index("ix_apartments_complex_id", "complex_id"),
        Index("ix_apartments_is_active", "is_active"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[str] = mapped_column(String(64), unique=True)
    url: Mapped[str] = mapped_column(String(512))
    complex_id: Mapped[int] = mapped_column(
        ForeignKey("residential_complexes.id", ondelete="CASCADE"),
    )
    price: Mapped[int] = mapped_column(Integer)
    price_per_sqm: Mapped[float] = mapped_column(Float)
    district: Mapped[str] = mapped_column(String(255), default="", server_default="")
    address: Mapped[str] = mapped_column(String(512), default="", server_default="")
    rooms: Mapped[int] = mapped_column(Integer)
    total_area: Mapped[float] = mapped_column(Float)
    living_area: Mapped[float | None] = mapped_column(Float, nullable=True)
    kitchen_area: Mapped[float | None] = mapped_column(Float, nullable=True)
    floor: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_floors: Mapped[int | None] = mapped_column(Integer, nullable=True)
    year_built: Mapped[int | None] = mapped_column(Integer, nullable=True)
    house_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    ceiling_height: Mapped[float | None] = mapped_column(Float, nullable=True)
    condition: Mapped[str | None] = mapped_column(String(100), nullable=True)
    balcony: Mapped[str | None] = mapped_column(String(100), nullable=True)
    bathroom: Mapped[str | None] = mapped_column(String(100), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    photos: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    seller_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    complex: Mapped[ResidentialComplex] = relationship(back_populates="apartments")
    prices: Mapped[list[ApartmentPrice]] = relationship(
        back_populates="apartment",
        cascade="all, delete-orphan",
    )
    status_history: Mapped[list[ApartmentStatusHistory]] = relationship(
        back_populates="apartment",
        cascade="all, delete-orphan",
    )
    sellers: Mapped[list[Seller]] = relationship(
        back_populates="apartment",
        cascade="all, delete-orphan",
    )
    notifications: Mapped[list[Notification]] = relationship(
        back_populates="apartment",
        cascade="all, delete-orphan",
    )


if TYPE_CHECKING:
    from app.models.notification import Notification
    from app.models.price_history import ApartmentPrice
    from app.models.residential_complex import ResidentialComplex
    from app.models.seller import Seller
    from app.models.status_history import ApartmentStatusHistory
