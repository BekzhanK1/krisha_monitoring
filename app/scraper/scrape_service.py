from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.models import Seller, SellerType
from app.repositories import apartment_repo, complex_repo, search_config_repo
from app.scraper.filters import SearchFilters
from app.scraper.krisha_scraper import KrishaScraper

RECENT_DETAIL_PARSE_HOURS = 1
DEFAULT_SEARCH_LABEL = "__search__"


@dataclass(slots=True)
class ScrapeResult:
    label: str
    total_found: int
    new: int = 0
    updated: int = 0
    unchanged: int = 0
    skipped_recent: int = 0
    errors: int = 0
    duration_sec: float = 0.0
    marked_inactive: int = 0


class ScrapeService:
    def __init__(
        self,
        session: AsyncSession,
        settings: Settings | None = None,
        max_listings: int | None = None,
    ) -> None:
        self._session = session
        self._settings = settings or get_settings()
        configured_max = self._settings.scraper_max_listings
        self._max_listings = max_listings if max_listings is not None else configured_max
        self._db_lock = asyncio.Lock()

    async def scrape_search(
        self,
        search_url: str,
        label: str = DEFAULT_SEARCH_LABEL,
    ) -> ScrapeResult:
        started = time.monotonic()
        result = ScrapeResult(label=label, total_found=0)
        seen_by_complex: dict[int, list[str]] = defaultdict(list)
        complex_names: dict[int, str] = {}

        async with KrishaScraper(headless=True) as scraper:
            listing_urls = await scraper.get_listing_urls(
                search_url,
                max_listings=self._max_listings,
            )

            result.total_found = len(listing_urls)
            semaphore = asyncio.Semaphore(3)

            async def process_url(url: str) -> None:
                async with semaphore:
                    await self._process_listing(
                        scraper=scraper,
                        url=url,
                        result=result,
                        seen_by_complex=seen_by_complex,
                        complex_names=complex_names,
                    )

            await asyncio.gather(*(process_url(url) for url in listing_urls))

        for complex_id, external_ids in seen_by_complex.items():
            complex_name = complex_names.get(complex_id, label)
            marked = await apartment_repo.mark_inactive(
                self._session,
                external_ids,
                complex_id,
                parser_interval_minutes=self._settings.parser_interval_minutes,
                complex_name=complex_name,
            )
            result.marked_inactive += len(marked)

        await self._session.commit()
        result.duration_sec = time.monotonic() - started
        logger.info(
            "Scrape '{}' finished: found={} new={} updated={} unchanged={} skipped={} "
            "errors={} inactive={} in {:.1f}s",
            label,
            result.total_found,
            result.new,
            result.updated,
            result.unchanged,
            result.skipped_recent,
            result.errors,
            result.marked_inactive,
            result.duration_sec,
        )
        return result

    async def scrape_all(self) -> list[ScrapeResult]:
        configs = await search_config_repo.get_active_configs(self._session)
        if not configs:
            await search_config_repo.get_or_create_default(self._session)
            await self._session.commit()
            configs = await search_config_repo.get_active_configs(self._session)

        if not configs:
            logger.warning("No active search configs in database")
            return []

        results: list[ScrapeResult] = []
        for config in configs:
            filters = SearchFilters.from_search_config(config)
            search_url = filters.build_url()
            logger.info("Scraping config '{}' with URL: {}", config.name, search_url)
            results.append(await self.scrape_search(search_url, label=config.name))
        return results

    async def _process_listing(
        self,
        *,
        scraper: KrishaScraper,
        url: str,
        result: ScrapeResult,
        seen_by_complex: dict[int, list[str]],
        complex_names: dict[int, str],
    ) -> None:
        from app.scraper.parser import _extract_external_id, parse_apartment_page

        listing_id = _extract_external_id(url)
        if listing_id is None:
            result.errors += 1
            logger.warning("Invalid listing URL, skipping: {}", url)
            return

        async with self._db_lock:
            existing = await apartment_repo.get_by_external_id(self._session, listing_id)
        now = datetime.now(UTC)
        recent_cutoff = now - timedelta(hours=RECENT_DETAIL_PARSE_HOURS)
        if existing is not None and existing.last_seen_at >= recent_cutoff:
            async with self._db_lock:
                existing.last_seen_at = now
                seen_by_complex[existing.complex_id].append(listing_id)
                complex_names.setdefault(existing.complex_id, "")
            result.skipped_recent += 1
            result.unchanged += 1
            return

        try:
            html = await scraper.fetch_page_html(url)
            parsed = parse_apartment_page(html, url)
            if parsed is None:
                result.errors += 1
                logger.warning("Failed to parse listing {}", url)
                return

            complex_name = (
                parsed.get("complex_name") or parsed.get("district") or DEFAULT_SEARCH_LABEL
            )

            async with self._db_lock:
                complex_ = await complex_repo.get_or_create(
                    self._session,
                    complex_name,
                    district=parsed.get("district", ""),
                )

                apartment_data = {
                    key: value
                    for key, value in parsed.items()
                    if key not in {"complex_name", "seller_name", "seller_phone"}
                }
                apartment_data["complex_id"] = complex_.id

                apartment, is_new, price_changed = await apartment_repo.upsert_apartment(
                    self._session,
                    apartment_data,
                )
                await self._upsert_seller(apartment.id, parsed)

                seen_by_complex[complex_.id].append(parsed["external_id"])
                complex_names[complex_.id] = complex_.name

            if is_new:
                result.new += 1
            elif price_changed:
                result.updated += 1
            else:
                result.unchanged += 1
        except Exception:
            result.errors += 1
            logger.exception("Error processing listing {}", url)

    async def _upsert_seller(self, apartment_id: int, parsed: dict[str, object]) -> None:
        seller_name = parsed.get("seller_name")
        seller_phone = parsed.get("seller_phone")
        seller_type_raw = parsed.get("seller_type")
        if not seller_name and not seller_phone and not seller_type_raw:
            return

        result = await self._session.execute(
            select(Seller).where(Seller.apartment_id == apartment_id),
        )
        seller = result.scalar_one_or_none()
        seller_type = SellerType(str(seller_type_raw)) if isinstance(seller_type_raw, str) else None

        if seller is None:
            self._session.add(
                Seller(
                    apartment_id=apartment_id,
                    name=str(seller_name) if isinstance(seller_name, str) else None,
                    phone=str(seller_phone) if isinstance(seller_phone, str) else None,
                    seller_type=seller_type,
                ),
            )
            return

        if isinstance(seller_name, str):
            seller.name = seller_name
        if isinstance(seller_phone, str):
            seller.phone = seller_phone
        if seller_type is not None:
            seller.seller_type = seller_type
