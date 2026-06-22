from app.models import SearchConfig
from app.scraper.filters import SearchFilters


def test_search_filters_omits_empty_params() -> None:
    filters = SearchFilters(city="astana")
    params = filters.to_query_params()
    assert params == {}
    assert filters.build_url() == "https://krisha.kz/prodazha/kvartiry/astana/"


def test_search_filters_includes_only_set_params() -> None:
    filters = SearchFilters(
        city="astana",
        rooms=2,
        price_to=30_000_000,
        text="Срочно",
    )
    params = filters.to_query_params()
    assert params["_txt_"] == "Срочно"
    assert params["das[live.rooms]"] == "2"
    assert params["das[price][to]"] == "30000000"
    assert "das[flat.floor][from]" not in params


def test_search_filters_from_config_skips_blank_text() -> None:
    config = SearchConfig(
        id=1,
        name="default",
        city="astana",
        rooms=3,
        text="   ",
    )
    filters = SearchFilters.from_search_config(config)
    assert filters.rooms == 3
    assert filters.text is None
    assert "_txt_" not in filters.to_query_params()


def test_search_filters_build_url_with_pagination() -> None:
    filters = SearchFilters(city="astana", rooms=2)
    page_one = filters.build_url()
    page_two = filters.build_url(page=2)
    assert page_one.endswith("/astana/?das%5Blive.rooms%5D=2") or page_one.endswith(
        "/astana/?das[live.rooms]=2",
    )
    assert "page=2" in page_two
