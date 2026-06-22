import uuid
from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import get_settings
from app.repositories import apartment_repo, complex_repo, price_repo


@pytest.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    get_settings.cache_clear()
    engine = create_async_engine(
        get_settings().database_url,
        poolclass=NullPool,
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()
    await engine.dispose()


def _apartment_data(complex_id: int, external_id: str) -> dict:
    return {
        "external_id": external_id,
        "url": f"https://krisha.kz/a/show/{external_id}",
        "complex_id": complex_id,
        "price": 45_000_000,
        "price_per_sqm": 450_000.0,
        "district": "Esil",
        "address": "Test Street 1",
        "rooms": 2,
        "total_area": 100.0,
    }


@pytest.mark.asyncio
async def test_complex_repo_get_or_create_and_get_all(db_session: AsyncSession) -> None:
    suffix = uuid.uuid4().hex[:8]
    name = f"Test Complex {suffix}"

    created = await complex_repo.get_or_create(db_session, name, district="Esil")
    assert created.name == name
    assert created.district == "Esil"

    again = await complex_repo.get_or_create(db_session, name, district="Other")
    assert again.id == created.id

    all_complexes = await complex_repo.get_all(db_session)
    assert any(complex_.id == created.id for complex_ in all_complexes)


@pytest.mark.asyncio
async def test_apartment_repo_upsert_and_queries(db_session: AsyncSession) -> None:
    suffix = uuid.uuid4().hex[:8]
    complex_ = await complex_repo.get_or_create(db_session, f"Apt Complex {suffix}")
    external_id = f"test-{suffix}"

    apartment, is_new, price_changed = await apartment_repo.upsert_apartment(
        db_session,
        _apartment_data(complex_.id, external_id),
    )
    assert is_new is True
    assert price_changed is False
    assert apartment.external_id == external_id

    found = await apartment_repo.get_by_external_id(db_session, external_id)
    assert found is not None
    assert found.id == apartment.id

    active = await apartment_repo.get_active_by_complex(db_session, complex_.id)
    assert any(item.id == apartment.id for item in active)

    updated_data = _apartment_data(complex_.id, external_id)
    updated_data["price"] = 44_000_000
    updated_data["price_per_sqm"] = 440_000.0

    updated, is_new, price_changed = await apartment_repo.upsert_apartment(
        db_session,
        updated_data,
    )
    assert is_new is False
    assert price_changed is True
    assert updated.price == 44_000_000

    history = await price_repo.get_price_history(db_session, apartment.id)
    assert len(history) >= 2


@pytest.mark.asyncio
async def test_apartment_repo_mark_inactive(db_session: AsyncSession) -> None:
    suffix = uuid.uuid4().hex[:8]
    complex_ = await complex_repo.get_or_create(db_session, f"Inactive Complex {suffix}")

    kept_id = f"keep-{suffix}"
    removed_id = f"remove-{suffix}"

    await apartment_repo.upsert_apartment(db_session, _apartment_data(complex_.id, kept_id))
    removed, _, _ = await apartment_repo.upsert_apartment(
        db_session,
        _apartment_data(complex_.id, removed_id),
    )

    marked = await apartment_repo.mark_inactive(db_session, [kept_id], complex_.id)
    assert len(marked) == 1
    assert marked[0].external_id == removed_id
    assert marked[0].is_active is False

    active = await apartment_repo.get_active_by_complex(db_session, complex_.id)
    assert all(item.external_id != removed_id for item in active)
    assert removed.external_id == removed_id
