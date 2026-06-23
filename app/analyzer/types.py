from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SaleVelocity:
    sold_last_30d: int
    avg_days_on_market: float | None
    median_days_on_market: float | None
