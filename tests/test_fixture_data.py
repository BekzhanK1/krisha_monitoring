from app.models import Apartment
from app.utils.fixture_data import is_fixture_apartment


def _apartment(*, address: str = "Test Street", complex_name: str = "Hunter Complex abc") -> Apartment:
    from unittest.mock import MagicMock

    complex_ = MagicMock()
    complex_.name = complex_name
    apartment = Apartment(
        id=1,
        external_id="140327335",
        url="https://krisha.kz/a/show/140327335",
        complex_id=1,
        price=35_000_000,
        price_per_sqm=350_000,
        district="Esil",
        address=address,
        rooms=2,
        total_area=100.0,
        is_active=True,
    )
    apartment.complex = complex_
    return apartment


def test_fixture_by_test_street_address() -> None:
    assert is_fixture_apartment(_apartment()) is True


def test_fixture_by_hunter_complex_name() -> None:
    assert is_fixture_apartment(_apartment(address="Real Street 1")) is True


def test_real_apartment_not_fixture() -> None:
    assert (
        is_fixture_apartment(
            _apartment(address="Кабанбай батыра 12", complex_name="EXPO Residence"),
        )
        is False
    )
