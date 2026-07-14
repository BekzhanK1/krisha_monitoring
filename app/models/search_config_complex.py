from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class SearchConfigComplex(Base):
    """Krisha.kz residential complex watchlist entry for a search config."""

    __tablename__ = "search_config_complexes"
    __table_args__ = (
        UniqueConstraint(
            "search_config_id",
            "krisha_complex_id",
            name="uq_search_config_complexes_config_krisha_id",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    search_config_id: Mapped[int] = mapped_column(
        ForeignKey("search_configs.id", ondelete="CASCADE"),
        index=True,
    )
    krisha_complex_id: Mapped[str] = mapped_column(String(64))
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    search_config: Mapped[SearchConfig] = relationship(back_populates="complexes")


if TYPE_CHECKING:
    from app.models.search_config import SearchConfig
