from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.analyzer.report_builder import build_market_report
from app.models import ApartmentStatus, ApartmentStatusHistory
from app.repositories import apartment_repo, complex_repo, score_repo


def _apartment_data(complex_id: int, external_id: str, *, price: int = 50_000_000) -> dict:
    return {
        "external_id": external_id,
        "url": f"https://krisha.kz/a/show/{external_id}",
        "complex_id": complex_id,
        "price": price,
        "price_per_sqm": 500_000,
        "district": "Esil",
        "address": "Test Street",
        "rooms": 2,
        "total_area": 100.0,
    }


@pytest.mark.asyncio
async def test_build_market_report_includes_sections(db_session: AsyncSession) -> None:
    suffix = uuid.uuid4().hex[:8]
    complex_ = await complex_repo.get_or_create(db_session, f"Report Complex {suffix}")
    external_id = str(200_000_000 + int(suffix[:6], 16) % 1_000_000)
    apartment, _, _ = await apartment_repo.upsert_apartment(
        db_session,
        _apartment_data(complex_.id, external_id, price=45_000_000),
    )
    apartment.first_seen_at = datetime.now(UTC) - timedelta(days=1)
    await score_repo.upsert_score(
        db_session,
        apartment.id,
        {
            "grade": "A+",
            "score": 92.0,
            "discount_pct": 15.0,
            "roi_pct": 11.0,
            "owner_probability": 0.8,
            "recommendation": "Тест A+.",
            "calculated_at": datetime.now(UTC),
        },
    )
    await db_session.flush()

    report = await build_market_report(db_session, days=7)

    assert "Отчёт по рынку" in report
    assert "Новые объявления" in report
    assert "Снятые объявления" in report
    assert "ТОП-3 ЖК по продажам" in report
    assert "ТОП-3 квартиры по рейтингу" in report
    assert "A+" in report


@pytest.mark.asyncio
async def test_build_market_report_counts_inactive_in_period(db_session: AsyncSession) -> None:
    suffix = uuid.uuid4().hex[:8]
    complex_ = await complex_repo.get_or_create(db_session, f"Inactive Complex {suffix}")
    external_id = str(210_000_000 + int(suffix[:6], 16) % 1_000_000)
    apartment, _, _ = await apartment_repo.upsert_apartment(
        db_session,
        _apartment_data(complex_.id, external_id),
    )
    db_session.add(
        ApartmentStatusHistory(
            apartment_id=apartment.id,
            status=ApartmentStatus.INACTIVE,
            old_price=apartment.price,
            changed_at=datetime.now(UTC) - timedelta(days=2),
        ),
    )
    await db_session.flush()

    report = await build_market_report(db_session, days=7)

    assert "Снятые объявления:</b> 1" in report


@pytest.mark.asyncio
async def test_build_market_report_top_complexes_by_sold(db_session: AsyncSession) -> None:
    suffix = uuid.uuid4().hex[:8]
    sold_complex = await complex_repo.get_or_create(db_session, f"Sold Leader {suffix}")
    other_complex = await complex_repo.get_or_create(db_session, f"Sold Other {suffix}")
    base_id = 220_000_000 + int(suffix[:6], 16) % 1_000_000

    for index, complex_ in enumerate((sold_complex, sold_complex, other_complex)):
        apartment, _, _ = await apartment_repo.upsert_apartment(
            db_session,
            _apartment_data(complex_.id, str(base_id + index)),
        )
        db_session.add(
            ApartmentStatusHistory(
                apartment_id=apartment.id,
                status=ApartmentStatus.INACTIVE,
                old_price=apartment.price,
                changed_at=datetime.now(UTC) - timedelta(days=1),
            ),
        )
    await db_session.flush()

    report = await build_market_report(db_session, days=7)

    assert sold_complex.name in report
    assert "— 2" in report
