from app.scraper.urls import is_valid_listing_id, listing_url


def test_listing_url_valid_id() -> None:
    assert listing_url("1011098178") == "https://krisha.kz/a/show/1011098178"


def test_listing_url_rejects_invalid_id() -> None:
    assert listing_url("top-23427236") is None
    assert listing_url("") is None


def test_is_valid_listing_id() -> None:
    assert is_valid_listing_id("1011098178") is True
    assert is_valid_listing_id("top-abc") is False
