from __future__ import annotations

import html
from datetime import UTC, datetime, timedelta

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Apartment, ApartmentStatus, ApartmentStatusHistory, ResidentialComplex
from app.repositories import score_repo
from app.scraper.urls import is_valid_listing_id, listing_url


async def build_market_report(session: AsyncSession, *, days: int = 7) -> str:
    """Return HTML report text for Telegram."""
    cutoff = datetime.now(UTC) - timedelta(days=days)
    now = datetime.now(UTC)
    date_label = now.strftime("%d.%m.%Y")

    new_stats = await session.execute(
        select(func.count(Apartment.id), func.avg(Apartment.price)).where(
            Apartment.first_seen_at >= cutoff,
            Apartment.external_id.regexp_match("^[0-9]+$"),
        ),
    )
    new_count, new_avg_price = new_stats.one()
    new_count = int(new_count or 0)
    avg_price_mln = (float(new_avg_price or 0)) / 1_000_000

    inactive_result = await session.execute(
        select(func.count(ApartmentStatusHistory.id)).where(
            ApartmentStatusHistory.status == ApartmentStatus.INACTIVE,
            ApartmentStatusHistory.changed_at >= cutoff,
        ),
    )
    inactive_count = int(inactive_result.scalar_one() or 0)

    sold_result = await session.execute(
        select(ResidentialComplex.name, func.count(ApartmentStatusHistory.id).label("sold"))
        .select_from(ApartmentStatusHistory)
        .join(Apartment, Apartment.id == ApartmentStatusHistory.apartment_id)
        .join(ResidentialComplex, ResidentialComplex.id == Apartment.complex_id)
        .where(
            ApartmentStatusHistory.status == ApartmentStatus.INACTIVE,
            ApartmentStatusHistory.changed_at >= cutoff,
        )
        .group_by(ResidentialComplex.id, ResidentialComplex.name)
        .order_by(desc("sold"), ResidentialComplex.name)
        .limit(3),
    )
    top_complexes = list(sold_result.all())

    top_scores = await score_repo.get_top_by_grade(session, limit=3)

    lines = [
        f"<b>📊 Отчёт по рынку</b> — {html.escape(date_label)}",
        f"Период: {days} дн.",
        "",
        f"<b>Новые объявления:</b> {new_count}",
        f"Средняя цена: {avg_price_mln:.1f} млн" if new_count else "Средняя цена: —",
        "",
        f"<b>Снятые объявления:</b> {inactive_count}",
        "",
        "<b>ТОП-3 ЖК по продажам:</b>",
    ]
    if top_complexes:
        for index, (name, sold) in enumerate(top_complexes, start=1):
            lines.append(f"{index}. {html.escape(name)} — {int(sold)}")
    else:
        lines.append("—")

    lines.extend(["", "<b>ТОП-3 квартиры по рейтингу:</b>"])
    if top_scores:
        for index, scored in enumerate(top_scores, start=1):
            apartment = scored.apartment
            if not is_valid_listing_id(apartment.external_id):
                continue
            complex_name = apartment.complex.name if apartment.complex is not None else "—"
            price_mln = apartment.price / 1_000_000
            url = listing_url(apartment.external_id)
            link = (
                f'<a href="{html.escape(url, quote=True)}">объявление</a>'
                if url is not None
                else "—"
            )
            lines.append(
                f"{index}. ⭐ {html.escape(scored.grade)} | "
                f"{html.escape(complex_name)} | {price_mln:.0f} млн | ROI {scored.roi_pct:.0f}% | "
                f"{link}",
            )
    else:
        lines.append("—")

    return "\n".join(lines)
