from __future__ import annotations

import pytest

from app.telegram.settings_validation import validate_field_value


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("30000000", 30_000_000),
        ("30 000 000", 30_000_000),
        ("-", None),
    ],
)
def test_validate_price_to(raw: str, expected: int | None) -> None:
    value, error = validate_field_value("price_to", raw)
    assert error is None
    assert value == expected


@pytest.mark.parametrize("raw", ["0", "abc", "600000000"])
def test_validate_price_to_rejects_invalid(raw: str) -> None:
    _, error = validate_field_value("price_to", raw)
    assert error is not None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2", 2),
        ("-", None),
    ],
)
def test_validate_rooms(raw: str, expected: int | None) -> None:
    value, error = validate_field_value("rooms", raw)
    assert error is None
    assert value == expected


def test_validate_rooms_rejects_out_of_range() -> None:
    _, error = validate_field_value("rooms", "11")
    assert error is not None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("45", 45.0),
        ("45,5", 45.5),
        ("-", None),
    ],
)
def test_validate_area_from(raw: str, expected: float | None) -> None:
    value, error = validate_field_value("area_from", raw)
    assert error is None
    assert value == expected


def test_validate_area_range_order() -> None:
    _, error = validate_field_value("area_from", "80", area_to=50.0)
    assert error is not None

    _, error = validate_field_value("area_to", "40", area_from=50.0)
    assert error is not None


def test_validate_text_accepts_phrase() -> None:
    value, error = validate_field_value("text", "Срочно")
    assert error is None
    assert value == "Срочно"


def test_validate_text_clear_with_dash() -> None:
    value, error = validate_field_value("text", "-")
    assert error is None
    assert value is None


def test_validate_unknown_field() -> None:
    _, error = validate_field_value("city", "astana")
    assert error is not None
