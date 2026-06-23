from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class MarketAnalytics(Base):
    __tablename__ = "analytics"
    __table_args__ = (
        Index("ix_analytics_complex_id_calculated_at", "complex_id", "calculated_at"),
        Index("ix_analytics_district_calculated_at", "district", "calculated_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    complex_id: Mapped[int | None] = mapped_column(
        ForeignKey("residential_complexes.id", ondelete="SET NULL"),
        nullable=True,
    )
    district: Mapped[str | None] = mapped_column(String(255), nullable=True)
    rooms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    median_price: Mapped[int] = mapped_column(Integer)
    avg_price: Mapped[int] = mapped_column(Integer)
    median_price_per_sqm: Mapped[int] = mapped_column(Integer)
    avg_price_per_sqm: Mapped[float] = mapped_column(Float)
    active_count: Mapped[int] = mapped_column(Integer)
    sold_last_30d: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    avg_days_on_market: Mapped[float | None] = mapped_column(Float, nullable=True)
    calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    complex: Mapped[ResidentialComplex | None] = relationship()


if TYPE_CHECKING:
    from app.models.residential_complex import ResidentialComplex
