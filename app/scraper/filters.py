from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from urllib.parse import quote, urlencode

if TYPE_CHECKING:
    from app.models.search_config import SearchConfig

BASE_LISTING_URL = "https://krisha.kz/prodazha/kvartiry"


@dataclass(frozen=True, slots=True)
class SearchFilters:
    city: str = "astana"
    rooms: int | None = None
    price_from: int | None = None
    price_to: int | None = None
    floor_from: int | None = None
    floor_to: int | None = None
    building_floors_from: int | None = None
    building_floors_to: int | None = None
    year_from: int | None = None
    year_to: int | None = None
    area_from: float | None = None
    area_to: float | None = None
    text: str | None = None
    complex_ids: tuple[str, ...] = ()

    @classmethod
    def from_search_config(cls, config: SearchConfig) -> SearchFilters:
        text = config.text.strip() if config.text and config.text.strip() else None
        complex_ids: list[str] = []
        for item in getattr(config, "complexes", []) or []:
            krisha_id = (item.krisha_complex_id or "").strip()
            if krisha_id and krisha_id not in complex_ids:
                complex_ids.append(krisha_id)
        # Backward compat: legacy single column
        if not complex_ids and config.complex_id and config.complex_id.strip():
            complex_ids.append(config.complex_id.strip())
        return cls(
            city=config.city or "astana",
            rooms=config.rooms,
            price_from=config.price_from,
            price_to=config.price_to,
            floor_from=config.floor_from,
            floor_to=config.floor_to,
            building_floors_from=config.building_floors_from,
            building_floors_to=config.building_floors_to,
            year_from=config.year_from,
            year_to=config.year_to,
            area_from=config.area_from,
            area_to=config.area_to,
            text=text,
            complex_ids=tuple(complex_ids),
        )

    def to_query_params(self, *, complex_id: str | None = None) -> dict[str, str]:
        params: dict[str, str] = {}
        if self.text:
            params["_txt_"] = self.text
        if self.rooms is not None:
            params["das[live.rooms]"] = str(self.rooms)
        if self.price_from is not None:
            params["das[price][from]"] = str(self.price_from)
        if self.price_to is not None:
            params["das[price][to]"] = str(self.price_to)
        if self.floor_from is not None:
            params["das[flat.floor][from]"] = str(self.floor_from)
        if self.floor_to is not None:
            params["das[flat.floor][to]"] = str(self.floor_to)
        if self.building_floors_from is not None:
            params["das[house.floor_num][from]"] = str(self.building_floors_from)
        if self.building_floors_to is not None:
            params["das[house.floor_num][to]"] = str(self.building_floors_to)
        if self.year_from is not None:
            params["das[house.year][from]"] = str(self.year_from)
        if self.year_to is not None:
            params["das[house.year][to]"] = str(self.year_to)
        if self.area_from is not None:
            params["das[live.square][from]"] = str(self.area_from)
        if self.area_to is not None:
            params["das[live.square][to]"] = str(self.area_to)
        if complex_id:
            params["das[map.complex]"] = complex_id
        return params

    def build_url(self, page: int = 1, *, complex_id: str | None = None) -> str:
        """Build one listing URL.

        If ``complex_id`` is omitted and there are multiple complexes,
        uses the first one (prefer ``build_urls`` / ``iter_search_targets``).
        """
        resolved_complex = complex_id
        if resolved_complex is None and len(self.complex_ids) == 1:
            resolved_complex = self.complex_ids[0]
        elif resolved_complex is None and len(self.complex_ids) > 1:
            resolved_complex = self.complex_ids[0]

        params = self.to_query_params(complex_id=resolved_complex)
        city = self.city or "astana"
        url = f"{BASE_LISTING_URL}/{city}/"
        if params:
            url += "?" + urlencode(params, quote_via=quote)
        if page > 1:
            separator = "&" if "?" in url else "?"
            url = f"{url}{separator}page={page}"
        return url

    def build_urls(self, page: int = 1) -> list[str]:
        """One URL per complex; if none — a single URL without complex filter."""
        if not self.complex_ids:
            return [self.build_url(page=page, complex_id=None)]
        return [self.build_url(page=page, complex_id=cid) for cid in self.complex_ids]

    def iter_search_targets(self) -> list[tuple[str, str]]:
        """Return ``(url, label)`` pairs for scraper runs."""
        if not self.complex_ids:
            return [(self.build_url(complex_id=None), "all")]
        return [
            (self.build_url(complex_id=cid), f"complex:{cid}")
            for cid in self.complex_ids
        ]


def append_page(search_url: str, page: int) -> str:
    if page <= 1:
        return search_url
    separator = "&" if "?" in search_url else "?"
    return f"{search_url}{separator}page={page}"
