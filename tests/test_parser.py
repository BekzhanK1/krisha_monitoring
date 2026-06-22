from pathlib import Path

import pytest

from app.scraper.parser import (
    _detect_seller_type,
    _extract_external_id,
    _parse_area,
    _parse_price,
    parse_apartment_page,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "listing_detail.html"
FIXTURE_URL = "https://krisha.kz/a/show/1006022667"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("22 400 000 ₸", 22_400_000),
        ("22&nbsp;400&nbsp;000&nbsp;", 22_400_000),
        ("", None),
        (None, None),
    ],
)
def test_parse_price(text: str | None, expected: int | None) -> None:
    assert _parse_price(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("44.4 м²", 44.4),
        ("44,4 м²", 44.4),
        ("", None),
    ],
)
def test_parse_area(text: str, expected: float | None) -> None:
    assert _parse_area(text) == expected


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://krisha.kz/a/show/1006022667", "1006022667"),
        ("https://krisha.kz/a/show/1006022667?foo=bar", "1006022667"),
        ("https://krisha.kz/prodazha/kvartiry/", None),
    ],
)
def test_extract_external_id(url: str, expected: str | None) -> None:
    assert _extract_external_id(url) == expected


@pytest.mark.parametrize(
    ("text", "seller_json", "expected"),
    [
        ("Крыша Агент Оспанова", {}, "agent"),
        ("агентство недвижимости", {}, "agency"),
        ("собственник", {}, "owner"),
        ("", {"type": "specialist"}, "agent"),
    ],
)
def test_detect_seller_type(text: str, seller_json: dict[str, str], expected: str) -> None:
    assert _detect_seller_type(text, seller_json) == expected


def test_parse_apartment_page_fixture() -> None:
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    parsed = parse_apartment_page(html, FIXTURE_URL)
    assert parsed is not None
    assert parsed["external_id"] == "1006022667"
    assert parsed["price"] == 22_400_000
    assert parsed["rooms"] == 2
    assert parsed["total_area"] == 44.4
    assert parsed["floor"] == 6
    assert parsed["total_floors"] == 10
    assert parsed["year_built"] == 2020
    assert parsed["complex_name"] == "Камшат"
    assert parsed["district"] == "Нура р-н"
    assert parsed["seller_name"] == "Оспанова Диана"
    assert parsed["seller_type"] == "agent"
    assert parsed["photos"]
    assert parsed["description"] is not None
    assert "Срочно" in parsed["description"]
