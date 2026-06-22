from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ResidentialComplex(Base):
    __tablename__ = "residential_complexes"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    district: Mapped[str] = mapped_column(String(255), default="", server_default="")
    city: Mapped[str] = mapped_column(String(100), default="Astana", server_default="Astana")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    apartments: Mapped[list[Apartment]] = relationship(
        back_populates="complex",
        cascade="all, delete-orphan",
    )


if TYPE_CHECKING:
    from app.models.apartment import Apartment
