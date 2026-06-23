from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ApartmentScore(Base):
    __tablename__ = "apartment_scores"
    __table_args__ = (Index("ix_apartment_scores_apartment_id", "apartment_id", unique=True),)

    id: Mapped[int] = mapped_column(primary_key=True)
    apartment_id: Mapped[int] = mapped_column(
        ForeignKey("apartments.id", ondelete="CASCADE"),
        unique=True,
    )
    grade: Mapped[str] = mapped_column(String(8))
    score: Mapped[float] = mapped_column(Float)
    discount_pct: Mapped[float] = mapped_column(Float)
    roi_pct: Mapped[float] = mapped_column(Float)
    owner_probability: Mapped[float | None] = mapped_column(Float, nullable=True)
    recommendation: Mapped[str] = mapped_column(Text)
    calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    apartment: Mapped[Apartment] = relationship()


if TYPE_CHECKING:
    from app.models.apartment import Apartment
