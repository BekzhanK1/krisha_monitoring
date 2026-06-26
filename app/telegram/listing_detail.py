"""Formatters for detailed apartment listing views."""
from __future__ import annotations

import html
from datetime import datetime

from app.models.apartment import Apartment
from app.models.apartment_score import ApartmentScore
from app.models.price_history import ApartmentPrice
from app.scraper.urls import listing_url


def _format_price_mln(price: int) -> str:
    mln = price / 1_000_000
    if abs(mln - round(mln)) < 0.05:
        return f"{int(round(mln))} млн"
    return f"{mln:.1f} млн"


def _format_price_history(prices: list[ApartmentPrice], limit: int = 5) -> str:
    if not prices:
        return "История цен недоступна"
    recent = sorted(prices, key=lambda p: p.recorded_at, reverse=True)[:limit]
    lines: list[str] = []
    for entry in recent:
        date_str = entry.recorded_at.strftime("%d.%m.%Y")
        lines.append(f"  • {date_str}: {_format_price_mln(entry.price)}")
    return "\n".join(lines)


def format_apartment_detail(
    apartment: Apartment,
    *,
    score: ApartmentScore | None = None,
    is_favorite: bool = False,
    prices: list[ApartmentPrice] | None = None,
) -> str:
    """Format a full apartment detail message with all available info."""
    complex_name = apartment.complex.name if apartment.complex is not None else "—"
    url = listing_url(apartment.external_id)
    safe_url = html.escape(url, quote=True) if url else ""

    floor = "—"
    if apartment.floor is not None and apartment.total_floors is not None:
        floor = f"{apartment.floor}/{apartment.total_floors}"
    elif apartment.floor is not None:
        floor = str(apartment.floor)

    lines = [
        f"🏢 <b>{html.escape(complex_name)}</b>",
        f"💰 Цена: <b>{_format_price_mln(apartment.price)}</b> "
        f"({apartment.price_per_sqm:,.0f} ₸/м²)".replace(",", " "),
        f"📐 Площадь: {apartment.total_area:.1f} м²",
        f"🚪 Комнат: {apartment.rooms}",
        f"🏢 Этаж: {floor}",
    ]

    if apartment.year_built is not None:
        lines.append(f"📅 Год: {apartment.year_built}")

    if apartment.house_type:
        lines.append(f"🏠 Тип: {html.escape(apartment.house_type)}")

    if apartment.condition:
        lines.append(f"🔧 Состояние: {html.escape(apartment.condition)}")

    if apartment.district:
        lines.append(f"📍 Район: {html.escape(apartment.district)}")

    if apartment.seller_type:
        lines.append(f"👤 Продавец: {html.escape(apartment.seller_type)}")

    if score is not None:
        lines.append("")
        lines.append(f"⭐ Рейтинг: <b>{html.escape(score.grade)}</b> (score: {score.score:.1f})")
        lines.append(f"📉 Скидка: {score.discount_pct:.0f}%")
        lines.append(f"📈 ROI: ~{score.roi_pct:.0f}%")
        if score.recommendation:
            lines.append(f"💡 {html.escape(score.recommendation)}")

    if prices:
        lines.append("")
        lines.append("📊 <b>История цен:</b>")
        lines.append(_format_price_history(prices))

    if apartment.description:
        desc = apartment.description[:500]
        if len(apartment.description) > 500:
            desc += "…"
        lines.append("")
        lines.append(f"📝 {html.escape(desc)}")

    if safe_url:
        lines.append("")
        lines.append(f'<a href="{safe_url}">🔗 Открыть на Krisha.kz</a>')

    fav_icon = "⭐ " if is_favorite else ""
    lines.insert(0, f"{fav_icon}🏠 <b>Объявление</b>")
    lines.append("")

    return "\n".join(lines)
