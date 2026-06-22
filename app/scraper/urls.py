from __future__ import annotations

KRISHA_LISTING_BASE = "https://krisha.kz/a/show"


def is_valid_listing_id(listing_id: str) -> bool:
    """Krisha listing IDs are numeric (e.g. 1011098178)."""
    return listing_id.isdigit()


def listing_url(listing_id: str) -> str | None:
    if not is_valid_listing_id(listing_id):
        return None
    return f"{KRISHA_LISTING_BASE}/{listing_id}"
