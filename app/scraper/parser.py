from __future__ import annotations

import json
import re
from typing import Any

from bs4 import BeautifulSoup, Tag

from app.scraper.urls import listing_url

FIELD_MAP = {
    "Этаж": "floor",
    "Этажей в доме": "total_floors",
    "Год постройки": "year_built",
    "Тип дома": "house_type",
    "Высота потолков": "ceiling_height",
    "Состояние": "condition",
    "Балкон": "balcony",
    "Санузел": "bathroom",
    "Площадь": "total_area",
    "Жилая площадь": "living_area",
    "Площадь кухни": "kitchen_area",
}

TITLE_PATTERN = re.compile(
    r"(?P<rooms>\d+)-комнатная.*?·\s*(?P<area>[\d.,]+)\s*м².*?·\s*"
    r"(?P<floor>\d+)\s*/\s*(?P<total_floors>\d+)\s*этаж",
    re.IGNORECASE,
)
FLOOR_PATTERN = re.compile(r"(?P<floor>\d+)\s*(?:из|/)\s*(?P<total_floors>\d+)")
LISTING_ID_PATTERN = re.compile(r"/a/show/(\d+)")
PRICE_PER_SQM_PATTERN = re.compile(
    r"green-price[^>]*>\s*([\d\s&nbsp;]+)",
    re.IGNORECASE,
)


def parse_apartment_page(html: str, url: str) -> dict[str, Any] | None:
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        return None

    external_id = _extract_external_id(url)
    if external_id is None:
        return None

    advert_data = _extract_window_data(html)
    title_text = _text(soup.select_one(".offer__advert-title")) or ""
    price = _parse_price(_text(soup.select_one(".offer__price"))) or _price_from_json(advert_data)
    total_area = (
        _area_from_title(title_text)
        or _area_from_short_info(soup)
        or _area_from_json(
            advert_data,
        )
    )

    if price is None or total_area is None:
        return None

    rooms = _rooms_from_title(title_text) or _rooms_from_json(advert_data)
    if rooms is None:
        return None

    floor, total_floors = _floor_from_title(title_text)
    if floor is None:
        floor, total_floors = _floor_from_short_info(soup)

    fields = _parse_short_info(soup)
    parameters = _parse_parameters(soup)
    fields.update(parameters)

    district, address = _parse_location(soup)
    complex_name = _parse_complex_name(soup)
    description = _parse_description(soup)
    photos = _parse_photos(soup, advert_data)
    seller_name, seller_phone, seller_type = _parse_seller(soup, advert_data)

    price_per_sqm = _parse_price_per_sqm(html, price, total_area)

    return {
        "external_id": external_id,
        "url": listing_url(external_id) or url.split("?")[0],
        "price": price,
        "price_per_sqm": price_per_sqm,
        "complex_name": complex_name,
        "district": district,
        "address": address,
        "rooms": rooms,
        "total_area": total_area,
        "living_area": fields.get("living_area"),
        "kitchen_area": fields.get("kitchen_area"),
        "floor": floor if floor is not None else fields.get("floor"),
        "total_floors": total_floors if total_floors is not None else fields.get("total_floors"),
        "year_built": fields.get("year_built"),
        "house_type": fields.get("house_type"),
        "ceiling_height": fields.get("ceiling_height"),
        "condition": fields.get("condition"),
        "balcony": fields.get("balcony"),
        "bathroom": fields.get("bathroom"),
        "description": description,
        "photos": photos,
        "seller_name": seller_name,
        "seller_phone": seller_phone,
        "seller_type": seller_type,
    }


def _extract_external_id(url: str) -> str | None:
    match = LISTING_ID_PATTERN.search(url)
    return match.group(1) if match else None


def _parse_price(text: str | None) -> int | None:
    if not text:
        return None
    digits = re.sub(r"[^\d]", "", text.replace("\xa0", "").replace("&nbsp;", ""))
    if not digits:
        return None
    return int(digits)


def _parse_area(text: str | None) -> float | None:
    if not text:
        return None
    normalized = text.replace(",", ".").replace("\xa0", " ")
    match = re.search(r"([\d.]+)", normalized)
    if not match:
        return None
    return float(match.group(1))


def _parse_int(text: str | None) -> int | None:
    if not text:
        return None
    match = re.search(r"(\d+)", text.replace("\xa0", " "))
    return int(match.group(1)) if match else None


def _parse_float(text: str | None) -> float | None:
    if not text:
        return None
    normalized = text.replace(",", ".").replace("\xa0", " ")
    match = re.search(r"([\d.]+)", normalized)
    return float(match.group(1)) if match else None


def _text(element: Tag | None) -> str | None:
    if element is None:
        return None
    return element.get_text(" ", strip=True)


def _extract_window_data(html: str) -> dict[str, Any]:
    match = re.search(r"window\.data\s*=\s*(\{.*?\});", html, re.DOTALL)
    if not match:
        return {}
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError:
        return {}
    advert = payload.get("advert")
    return advert if isinstance(advert, dict) else {}


def _price_from_json(advert_data: dict[str, Any]) -> int | None:
    price = advert_data.get("price")
    return int(price) if isinstance(price, int | float) else None


def _area_from_json(advert_data: dict[str, Any]) -> float | None:
    area = advert_data.get("square")
    if isinstance(area, int | float):
        return float(area)
    return None


def _rooms_from_json(advert_data: dict[str, Any]) -> int | None:
    rooms = advert_data.get("rooms")
    return int(rooms) if isinstance(rooms, int | float) else None


def _rooms_from_title(title_text: str) -> int | None:
    match = re.search(r"(\d+)-комнат", title_text)
    return int(match.group(1)) if match else None


def _area_from_title(title_text: str) -> float | None:
    match = TITLE_PATTERN.search(title_text)
    if match:
        return _parse_area(match.group("area"))
    match = re.search(r"([\d.,]+)\s*м²", title_text)
    return _parse_area(match.group(1)) if match else None


def _floor_from_title(title_text: str) -> tuple[int | None, int | None]:
    match = TITLE_PATTERN.search(title_text)
    if match:
        return int(match.group("floor")), int(match.group("total_floors"))
    match = FLOOR_PATTERN.search(title_text)
    if match:
        return int(match.group("floor")), int(match.group("total_floors"))
    return None, None


def _area_from_short_info(soup: BeautifulSoup) -> float | None:
    item = soup.select_one('.offer__info-item[data-name="live.square"] .offer__advert-short-info')
    return _parse_area(_text(item))


def _floor_from_short_info(soup: BeautifulSoup) -> tuple[int | None, int | None]:
    item = soup.select_one('.offer__info-item[data-name="flat.floor"] .offer__advert-short-info')
    text = _text(item)
    if not text:
        return None, None
    match = FLOOR_PATTERN.search(text)
    if match:
        return int(match.group("floor")), int(match.group("total_floors"))
    return None, None


def _parse_short_info(soup: BeautifulSoup) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for item in soup.select(".offer__info-item"):
        title = _text(item.select_one(".offer__info-title"))
        value_element = item.select_one(".offer__advert-short-info")
        if not title or value_element is None:
            continue
        if title == "Жилой комплекс":
            continue
        field = FIELD_MAP.get(title)
        if field is None:
            continue
        value_text = _text(value_element)
        if field in {"floor", "total_floors", "year_built"}:
            if field == "floor" and value_text:
                floor_match = FLOOR_PATTERN.search(value_text)
                if floor_match:
                    result["floor"] = int(floor_match.group("floor"))
                    result["total_floors"] = int(floor_match.group("total_floors"))
            else:
                result[field] = _parse_int(value_text)
        elif field in {"total_area", "living_area", "kitchen_area", "ceiling_height"}:
            result[field] = _parse_float(value_text)
        else:
            result[field] = value_text
    return result


def _parse_parameters(soup: BeautifulSoup) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for dl in soup.select(".offer__parameters dl"):
        dt = dl.find("dt")
        dd = dl.find("dd")
        if dt is None or dd is None:
            continue
        label = _text(dt)
        value_text = _text(dd)
        if not label:
            continue
        field = FIELD_MAP.get(label)
        if field is None:
            continue
        if field in {"ceiling_height", "total_area", "living_area", "kitchen_area"}:
            result[field] = _parse_float(value_text)
        elif field in {"floor", "total_floors", "year_built"}:
            result[field] = _parse_int(value_text)
        else:
            result[field] = value_text
    return result


def _parse_location(soup: BeautifulSoup) -> tuple[str, str]:
    location = _text(soup.select_one(".offer__location span")) or ""
    district = ""
    address = location
    if "," in location:
        parts = [part.strip() for part in location.split(",") if part.strip()]
        if len(parts) >= 2:
            district = parts[1]
            address = ", ".join(parts[2:]) if len(parts) > 2 else parts[1]
        elif parts:
            district = parts[-1]
    elif location:
        district = location
    return district, address


def _parse_complex_name(soup: BeautifulSoup) -> str | None:
    item = soup.select_one('.offer__info-item[data-name="map.complex"] .offer__advert-short-info')
    if item is None:
        return None
    link = item.find("a")
    if link is not None:
        return _text(link)
    return _text(item)


def _parse_description(soup: BeautifulSoup) -> str | None:
    description = soup.select_one(".js-description") or soup.select_one(".offer__description .text")
    return _text(description)


def _parse_photos(soup: BeautifulSoup, advert_data: dict[str, Any]) -> list[str]:
    photos: list[str] = []
    for img in soup.select(".gallery__main-image img, .a-gallery__main img"):
        src = img.get("src") or img.get("data-src")
        if isinstance(src, str) and src.startswith("http"):
            photos.append(src)

    if photos:
        return photos

    json_photos = advert_data.get("photos")
    if isinstance(json_photos, list):
        for item in json_photos:
            if isinstance(item, dict):
                src = item.get("src")
                if isinstance(src, str):
                    photos.append(src)
    return photos


def _parse_seller(
    soup: BeautifulSoup,
    advert_data: dict[str, Any],
) -> tuple[str | None, str | None, str]:
    seller_name = _text(soup.select_one(".owners__name"))
    phone_element = soup.select_one(".a-phones .phone")
    seller_phone = _text(phone_element)

    seller_block = soup.select_one(".offer__sidebar-contacts, .owners__item")
    seller_text = _text(seller_block) or ""
    agency_name = ""
    seller_json = advert_data.get("seller")
    if isinstance(seller_json, dict):
        if not seller_name and isinstance(seller_json.get("name"), str):
            seller_name = seller_json["name"]
        agency = seller_json.get("agency")
        if isinstance(agency, dict) and isinstance(agency.get("name"), str):
            agency_name = agency["name"]
            seller_text = f"{seller_text} {agency_name}"

    seller_json_data = seller_json if isinstance(seller_json, dict) else {}
    seller_type = _detect_seller_type(seller_text, seller_json_data)
    return seller_name, seller_phone, seller_type


def _detect_seller_type(seller_text: str, seller_json: dict[str, Any]) -> str:
    lowered = seller_text.lower()
    agency_markers = ("агентство", "риэлтор", "риелтор", "realty", "агентств")
    if any(marker in lowered for marker in agency_markers):
        return "agency"
    if "агент" in lowered or seller_json.get("type") in {"specialist", "agent", "pro"}:
        return "agent"
    return "owner"


def _parse_price_per_sqm(html: str, price: int, total_area: float) -> float:
    match = PRICE_PER_SQM_PATTERN.search(html)
    if match:
        parsed = _parse_price(match.group(1))
        if parsed is not None:
            return float(parsed)
    if total_area > 0:
        return round(price / total_area, 2)
    return 0.0
