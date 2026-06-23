from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories import apartment_repo, complex_repo, score_repo


def _apartment_data(complex_id: int, external_id: str) -> dict:
    return {
        "external_id": external_id,
        "url": f"https://krisha.kz/a/show/{external_id}",
        "complex_id": complex_id,
        "price": 50_000_000,
        "price_per_sqm": 500_000,
        "district": "Esil",
        "address": "Test Street",
        "rooms": 2,
        "total_area": 100.0,
    }


@pytest.mark.asyncio
async def test_upsert_score_inserts_and_updates(db_session: AsyncSession) -> None:
    suffix = uuid.uuid4().hex[:8]
    complex_ = await complex_repo.get_or_create(db_session, f"Repo Complex {suffix}")
    apartment, _, _ = await apartment_repo.upsert_apartment(
        db_session,
        _apartment_data(complex_.id, str(110_000_000 + int(suffix[:6], 16) % 1_000_000)),
    )
    await db_session.flush()

    created = await score_repo.upsert_score(
        db_session,
        apartment.id,
        {
            "grade": "B",
            "score": 60.0,
            "discount_pct": 8.0,
            "roi_pct": 5.5,
            "owner_probability": 0.7,
            "recommendation": "Рейтинг B: тест.",
            "calculated_at": datetime.now(UTC),
        },
    )
    assert created.id is not None
    assert created.grade == "B"

    updated = await score_repo.upsert_score(
        db_session,
        apartment.id,
        {
            "grade": "A",
            "score": 75.0,
            "discount_pct": 12.0,
            "roi_pct": 9.0,
            "owner_probability": 0.8,
            "recommendation": "Рейтинг A: обновлено.",
            "calculated_at": datetime.now(UTC),
        },
    )
    assert updated.id == created.id
    assert updated.grade == "A"
    assert updated.score == 75.0


@pytest.mark.asyncio
async def test_get_top_grades_orders_by_score(db_session: AsyncSession) -> None:
    suffix = uuid.uuid4().hex[:8]
    complex_ = await complex_repo.get_or_create(db_session, f"Top Grades Complex {suffix}")
    base_id = 120_000_000 + int(suffix[:6], 16) % 1_000_000
    now = datetime.now(UTC)

    for index, (grade, score) in enumerate([("A", 80.0), ("A+", 90.0), ("B", 55.0)]):
        apartment, _, _ = await apartment_repo.upsert_apartment(
            db_session,
            _apartment_data(complex_.id, str(base_id + index)),
        )
        await score_repo.upsert_score(
            db_session,
            apartment.id,
            {
                "grade": grade,
                "score": score,
                "discount_pct": 10.0,
                "roi_pct": 7.0,
                "owner_probability": 0.6,
                "recommendation": f"Рейтинг {grade}.",
                "calculated_at": now,
            },
        )
    await db_session.flush()

    top = await score_repo.get_top_grades(db_session, ["A+", "A"], limit=2)
    assert len(top) == 2
    assert top[0].grade == "A+"
    assert top[1].grade == "A"
