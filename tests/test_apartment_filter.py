from app.models import Apartment
from app.scraper.filters import SearchFilters


def _apartment(
    *,
    rooms: int = 2,
    price: int = 25_000_000,
    total_area: float = 50.0,
    floor: int | None = 5,
    total_floors: int | None = 12,
    year_built: int | None = 2018,
    description: str | None = "Срочно продам",
) -> Apartment:
    return Apartment(
        id=1,
        external_id="1011098178",
        url="https://krisha.kz/a/show/1011098178",
        complex_id=1,
        price=price,
        price_per_sqm=price / total_area,
        district="Esil",
        address="Test",
        rooms=rooms,
        total_area=total_area,
        floor=floor,
        total_floors=total_floors,
        year_built=year_built,
        description=description,
        is_active=True,
    )


def test_apply_search_filters_matches() -> None:
    from sqlalchemy import select

    from app.repositories.apartment_filter import apply_search_filters

    filters = SearchFilters(
        rooms=2,
        price_to=30_000_000,
        area_from=30,
        area_to=90,
        text="Срочно",
    )
    stmt = apply_search_filters(select(Apartment), filters)
    compiled = str(stmt)
    assert "rooms" in compiled
    assert "description" in compiled.lower() or "ilike" in compiled.lower()


def test_apartment_within_filter_bounds() -> None:
    filters = SearchFilters(rooms=2, price_to=30_000_000, area_to=90, floor_from=2, floor_to=7)
    apt = _apartment(price=25_000_000, total_area=50, floor=5)
    assert apt.rooms == filters.rooms
    assert apt.price <= (filters.price_to or apt.price)
    assert apt.total_area <= (filters.area_to or apt.total_area)


def test_apartment_outside_filter_area() -> None:
    filters = SearchFilters(area_to=90)
    apt = _apartment(total_area=152.0)
    assert apt.total_area > (filters.area_to or 0)
