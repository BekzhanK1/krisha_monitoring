from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories import search_config_complex_repo, search_config_repo
from app.scraper.filters import SearchFilters
from app.telegram.settings_handlers import parse_complex_input


def test_search_filters_multiple_complex_urls() -> None:
    filters = SearchFilters(
        city="astana",
        rooms=2,
        price_to=30_000_000,
        complex_ids=("111", "222"),
    )
    urls = filters.build_urls()
    assert len(urls) == 2
    assert "das%5Bmap.complex%5D=111" in urls[0] or "das[map.complex]=111" in urls[0]
    assert "das%5Bmap.complex%5D=222" in urls[1] or "das[map.complex]=222" in urls[1]
    assert all("das%5Blive.rooms%5D=2" in url or "das[live.rooms]=2" in url for url in urls)


def test_search_filters_iter_targets_without_complexes() -> None:
    targets = SearchFilters(city="astana").iter_search_targets()
    assert len(targets) == 1
    assert targets[0][1] == "all"
    assert "complex" not in targets[0][0]


def test_search_filters_from_config_reads_complexes() -> None:
    config = SimpleNamespace(
        city="astana",
        rooms=2,
        price_from=None,
        price_to=None,
        floor_from=None,
        floor_to=None,
        building_floors_from=None,
        building_floors_to=None,
        year_from=None,
        year_to=None,
        area_from=None,
        area_to=None,
        text=None,
        complex_id=None,
        complexes=[SimpleNamespace(krisha_complex_id="999", name="EXPO")],
    )
    filters = SearchFilters.from_search_config(config)  # type: ignore[arg-type]
    assert filters.complex_ids == ("999",)
    url = filters.build_url()
    assert "das%5Bmap.complex%5D=999" in url or "das[map.complex]=999" in url


def test_parse_complex_input() -> None:
    assert parse_complex_input("12345") == ("12345", None)
    assert parse_complex_input("12345|EXPO Residence") == ("12345", "EXPO Residence")
    assert parse_complex_input("12345 EXPO") == ("12345", "EXPO")
    assert parse_complex_input("abc") is None
    assert parse_complex_input("") is None


@pytest.mark.asyncio
async def test_add_and_remove_complexes(db_session: AsyncSession) -> None:
    config = await search_config_repo.get_or_create_default(db_session)
    config_id = config.id
    # Isolate from production watchlist seeded into the same DB.
    for row in await search_config_complex_repo.list_complexes(db_session, config_id):
        await search_config_complex_repo.remove_complex(
            db_session,
            config_id,
            row.krisha_complex_id,
        )
    await db_session.flush()

    await search_config_complex_repo.add_complex(
        db_session,
        config_id,
        "101",
        name="Alpha",
    )
    await search_config_complex_repo.add_complex(
        db_session,
        config_id,
        "202",
        name="Beta",
    )
    await search_config_complex_repo.add_complex(
        db_session,
        config_id,
        "101",
        name="Alpha Updated",
    )
    await db_session.flush()
    db_session.expire_all()

    rows = await search_config_complex_repo.list_complexes(db_session, config_id)
    assert len(rows) == 2
    assert {row.krisha_complex_id for row in rows} == {"101", "202"}
    alpha = next(row for row in rows if row.krisha_complex_id == "101")
    assert alpha.name == "Alpha Updated"

    reloaded = await search_config_repo.get_active_configs(db_session)
    assert len(reloaded) >= 1
    filters = SearchFilters.from_search_config(reloaded[0])
    assert set(filters.complex_ids) == {"101", "202"}
    assert len(filters.iter_search_targets()) == 2

    removed = await search_config_complex_repo.remove_complex(db_session, config_id, "101")
    assert removed is True
    remaining = await search_config_complex_repo.list_complexes(db_session, config_id)
    assert [row.krisha_complex_id for row in remaining] == ["202"]
