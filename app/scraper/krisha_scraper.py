from __future__ import annotations

import asyncio
import random
import re

from loguru import logger
from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright

from app.scraper.filters import append_page

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

LISTING_LINK_SELECTOR = 'a.a-card__title[href*="/a/show/"]'
LISTING_LINK_FALLBACK = 'a[href*="/a/show/"]'
NEXT_PAGE_SELECTOR = "a.paginator__btn--next"

RETRY_DELAYS_SEC = (5, 10, 20)
PAGE_DELAY_SEC = (1.0, 3.0)
LISTING_ID_PATTERN = re.compile(r"/a/show/(\d+)")


class KrishaScraper:
    def __init__(self, headless: bool = True) -> None:
        self._headless = headless
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None

    async def __aenter__(self) -> KrishaScraper:
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=self._headless)
        self._context = await self._browser.new_context(user_agent=USER_AGENT)
        return self

    async def __aexit__(self, *_exc: object) -> None:
        if self._context is not None:
            await self._context.close()
        if self._browser is not None:
            await self._browser.close()
        if self._playwright is not None:
            await self._playwright.stop()

    async def get_listing_urls(
        self,
        search_url: str,
        *,
        max_listings: int | None = None,
    ) -> list[str]:
        if self._context is None:
            msg = "KrishaScraper must be used as an async context manager"
            raise RuntimeError(msg)

        seen_ids: set[str] = set()
        ordered_urls: list[str] = []
        page_num = 1

        while True:
            page_url = append_page(search_url, page_num)
            html = await self._load_page(page_url)
            page_urls = self._extract_listing_urls(html)

            new_on_page = 0
            for url in page_urls:
                listing_id = self._extract_listing_id(url)
                if listing_id is None or listing_id in seen_ids:
                    continue
                seen_ids.add(listing_id)
                ordered_urls.append(url)
                new_on_page += 1

            logger.info(
                "Page {}: found {} listings ({} new)",
                page_num,
                len(page_urls),
                new_on_page,
            )

            if new_on_page == 0:
                break

            if max_listings is not None and len(ordered_urls) >= max_listings:
                break

            has_next = self._has_next_page(html)
            if not has_next and page_num > 1:
                break

            page_num += 1
            await asyncio.sleep(random.uniform(*PAGE_DELAY_SEC))

        if max_listings is not None:
            return ordered_urls[:max_listings]
        return ordered_urls

    async def fetch_page_html(self, url: str) -> str:
        return await self._load_page(url)

    async def _load_page(self, url: str) -> str:
        if self._context is None:
            msg = "KrishaScraper must be used as an async context manager"
            raise RuntimeError(msg)

        last_error: Exception | None = None
        for attempt, delay in enumerate(RETRY_DELAYS_SEC, start=1):
            page: Page | None = None
            try:
                page = await self._context.new_page()
                response = await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
                if response is not None and response.status >= 400:
                    msg = f"HTTP {response.status} for {url}"
                    raise RuntimeError(msg)
                await page.wait_for_timeout(1_500)
                return await page.content()
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Failed to load {} (attempt {}/{}): {}",
                    url,
                    attempt,
                    len(RETRY_DELAYS_SEC),
                    exc,
                )
                if attempt < len(RETRY_DELAYS_SEC):
                    await asyncio.sleep(delay)
            finally:
                if page is not None:
                    await page.close()

        msg = f"Failed to load {url} after {len(RETRY_DELAYS_SEC)} attempts"
        raise RuntimeError(msg) from last_error

    def _extract_listing_urls(self, html: str) -> list[str]:
        urls = self._extract_hrefs(html, LISTING_LINK_SELECTOR)
        if not urls:
            urls = self._extract_hrefs(html, LISTING_LINK_FALLBACK)

        normalized: list[str] = []
        seen: set[str] = set()
        for href in urls:
            full_url = self._normalize_listing_url(href)
            listing_id = self._extract_listing_id(full_url)
            if listing_id is None or listing_id in seen:
                continue
            seen.add(listing_id)
            normalized.append(full_url)
        return normalized

    @staticmethod
    def _extract_hrefs(html: str, selector: str) -> list[str]:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "lxml")
        hrefs: list[str] = []
        for element in soup.select(selector):
            href = element.get("href")
            if isinstance(href, str):
                hrefs.append(href)
        return hrefs

    @staticmethod
    def _normalize_listing_url(href: str) -> str:
        if href.startswith("http"):
            return href.split("?")[0]
        return f"https://krisha.kz{href.split('?')[0]}"

    @staticmethod
    def _extract_listing_id(url: str) -> str | None:
        match = LISTING_ID_PATTERN.search(url)
        return match.group(1) if match else None

    @staticmethod
    def _has_next_page(html: str) -> bool:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "lxml")
        return soup.select_one(NEXT_PAGE_SELECTOR) is not None
