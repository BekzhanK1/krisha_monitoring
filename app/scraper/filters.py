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
    complex_id: str | None = None

    @classmethod
    def from_search_config(cls, config: SearchConfig) -> SearchFilters:
        text = config.text.strip() if config.text and config.text.strip() else None
        complex_id = (
            config.complex_id.strip() if config.complex_id and config.complex_id.strip() else None
        )
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
            complex_id=complex_id,
        )

    def to_query_params(self) -> dict[str, str]:
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
        if self.complex_id:
            params["das[complex]"] = self.complex_id
        return params

    def build_url(self, page: int = 1) -> str:
        params = self.to_query_params()
        city = self.city or "astana"
        url = f"{BASE_LISTING_URL}/{city}/"
        if params:
            url += "?" + urlencode(params, quote_via=quote)
        if page > 1:
            separator = "&" if "?" in url else "?"
            url = f"{url}{separator}page={page}"
        return url


def append_page(search_url: str, page: int) -> str:
    if page <= 1:
        return search_url
    separator = "&" if "?" in search_url else "?"
    return f"{search_url}{separator}page={page}"
