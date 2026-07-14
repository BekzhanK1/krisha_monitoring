from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.search_config_complex import SearchConfigComplex


class SearchConfig(Base):
    """Параметры поиска на Krisha.kz. Редактируются через Telegram."""

    __tablename__ = "search_configs"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    city: Mapped[str] = mapped_column(String(100), default="astana", server_default="astana")
    rooms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    price_from: Mapped[int | None] = mapped_column(Integer, nullable=True)
    price_to: Mapped[int | None] = mapped_column(Integer, nullable=True)
    floor_from: Mapped[int | None] = mapped_column(Integer, nullable=True)
    floor_to: Mapped[int | None] = mapped_column(Integer, nullable=True)
    building_floors_from: Mapped[int | None] = mapped_column(Integer, nullable=True)
    building_floors_to: Mapped[int | None] = mapped_column(Integer, nullable=True)
    year_from: Mapped[int | None] = mapped_column(Integer, nullable=True)
    year_to: Mapped[int | None] = mapped_column(Integer, nullable=True)
    area_from: Mapped[float | None] = mapped_column(Float, nullable=True)
    area_to: Mapped[float | None] = mapped_column(Float, nullable=True)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Deprecated: use `complexes` relation. Kept for migration compatibility.
    complex_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    complexes: Mapped[list[SearchConfigComplex]] = relationship(
        back_populates="search_config",
        cascade="all, delete-orphan",
        order_by="SearchConfigComplex.id",
    )
