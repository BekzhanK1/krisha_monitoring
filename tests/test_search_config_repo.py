import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories import search_config_repo
from app.scraper.filters import SearchFilters


@pytest.mark.asyncio
async def test_get_or_create_default_config(db_session: AsyncSession) -> None:
    config = await search_config_repo.get_or_create_default(db_session)
    assert config.name == "default"
    assert config.city == "astana"
    assert config.rooms is None
    assert config.is_active is True

    filters = SearchFilters.from_search_config(config)
    assert filters.build_url() == "https://krisha.kz/prodazha/kvartiry/astana/"


@pytest.mark.asyncio
async def test_update_config_builds_partial_url(db_session: AsyncSession) -> None:
    await search_config_repo.get_or_create_default(db_session)
    config = await search_config_repo.update_config(
        db_session,
        "default",
        {
            "rooms": 2,
            "price_to": 30_000_000,
            "text": "Срочно",
            "floor_from": 2,
            "floor_to": 7,
        },
    )
    url = SearchFilters.from_search_config(config).build_url()
    assert "astana" in url
    assert "30000000" in url
    assert "_txt_" in url
    assert "das%5Bflat.floor%5D%5Bfrom%5D=2" in url or "das[flat.floor][from]=2" in url
    assert "das%5Bhouse.year%5D" not in url and "das[house.year]" not in url


@pytest.mark.asyncio
async def test_update_field_changes_single_value(db_session: AsyncSession) -> None:
    config = await search_config_repo.get_or_create_default(db_session)
    updated = await search_config_repo.update_field(db_session, config.id, "rooms", 3)
    assert updated.rooms == 3
