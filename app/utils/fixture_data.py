from __future__ import annotations

from app.models import Apartment

_TEST_ADDRESS_PREFIXES = ("test street",)
_TEST_COMPLEX_PREFIXES = (
    "hunter complex",
    "notify complex",
    "dedup complex",
    "stats complex",
    "median complex",
    "deal complex",
    "complex a ",
    "complex b ",
    "top complex",
    "new complex",
    "scoring complex",
    "analytics complex",
)


def is_fixture_apartment(apartment: Apartment) -> bool:
    """Detect apartments seeded by integration tests (must not trigger real alerts)."""
    address = (apartment.address or "").strip().lower()
    if any(address.startswith(prefix) for prefix in _TEST_ADDRESS_PREFIXES):
        return True
    complex_name = ""
    if apartment.complex is not None:
        complex_name = apartment.complex.name.lower()
    return any(complex_name.startswith(prefix) for prefix in _TEST_COMPLEX_PREFIXES)
