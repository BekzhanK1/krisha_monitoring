from __future__ import annotations

EDITABLE_FIELDS: frozenset[str] = frozenset(
    {"price_to", "rooms", "area_from", "area_to", "text"},
)

FIELD_LABELS: dict[str, str] = {
    "price_to": "Цена до",
    "rooms": "Комнаты",
    "area_from": "Площадь от",
    "area_to": "Площадь до",
    "text": "Текст",
}

CLEAR_VALUE = "-"

_MIN_PRICE = 1_000_000
_MAX_PRICE = 500_000_000
_MIN_ROOMS = 1
_MAX_ROOMS = 10
_MIN_AREA = 10.0
_MAX_AREA = 500.0


def validate_field_value(
    field: str,
    raw: str,
    *,
    area_from: float | None = None,
    area_to: float | None = None,
) -> tuple[object | None, str | None]:
    """Validate user input for a search_config field.

    Returns ``(value, error)``. On success ``error`` is None.
    Use value None to clear the field.
    """
    if field not in EDITABLE_FIELDS:
        return None, f"Неизвестное поле: {field}"

    text = raw.strip()
    if not text:
        return None, "Введите значение или «-» для сброса."

    if text == CLEAR_VALUE:
        if field == "text":
            return None, None
        return None, None

    if field == "text":
        return text, None

    if field == "price_to":
        return _validate_int_field(text, _MIN_PRICE, _MAX_PRICE, "цену")

    if field == "rooms":
        return _validate_int_field(text, _MIN_ROOMS, _MAX_ROOMS, "число комнат")

    if field in {"area_from", "area_to"}:
        value, error = _validate_float_field(text, _MIN_AREA, _MAX_AREA, "площадь")
        if error is not None:
            return None, error
        assert isinstance(value, float)
        new_from = value if field == "area_from" else area_from
        new_to = value if field == "area_to" else area_to
        if new_from is not None and new_to is not None and new_from > new_to:
            return None, "Площадь «от» не может быть больше «до»."
        return value, None

    return None, f"Неизвестное поле: {field}"


def _validate_int_field(
    text: str,
    min_value: int,
    max_value: int,
    label: str,
) -> tuple[int | None, str | None]:
    try:
        value = int(text.replace(" ", ""))
    except ValueError:
        return None, f"Укажите целое число для {label}."
    if value < min_value or value > max_value:
        return None, f"Значение должно быть от {min_value:,} до {max_value:,}.".replace(",", " ")
    return value, None


def _validate_float_field(
    text: str,
    min_value: float,
    max_value: float,
    label: str,
) -> tuple[float | None, str | None]:
    normalized = text.replace(",", ".").replace(" ", "")
    try:
        value = float(normalized)
    except ValueError:
        return None, f"Укажите число для {label}."
    if value < min_value or value > max_value:
        return None, f"Значение должно быть от {min_value:g} до {max_value:g}."
    return value, None
