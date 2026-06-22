from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    apartment_id: Mapped[int] = mapped_column(
        ForeignKey("apartments.id", ondelete="CASCADE"),
        index=True,
    )
    notification_type: Mapped[str] = mapped_column(String(100))
    message: Mapped[str] = mapped_column(Text)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_sent: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    apartment: Mapped[Apartment] = relationship(back_populates="notifications")


if TYPE_CHECKING:
    from app.models.apartment import Apartment
