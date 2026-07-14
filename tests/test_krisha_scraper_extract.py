from app.scraper.krisha_scraper import KrishaScraper

EMPTY_HTML = """
<html><body>
  <div class="a-search-empty"><div>Совпадений не найдено</div></div>
  <aside>
    <a href="/a/show/111111111">Рекомендуем</a>
    <a class="a-card__title" href="/a/show/222222222">Фейк из сайдбара</a>
  </aside>
</body></html>
"""

# Krisha puts "Совпадений не найдено" inside the complex selectbox even when results exist.
SELECTBOX_NOT_FOUND_HTML = """
<html><body>
  <ul class="selectbox-options">
    <li class="system search"><div class="not-found">Совпадений не найдено</div></li>
  </ul>
  <div class="a-list">
    <a class="a-card__title" href="/a/show/333333333">Квартира 1</a>
  </div>
</body></html>
"""

CARDS_HTML = """
<html><body>
  <div class="a-list">
    <a class="a-card__title" href="/a/show/333333333">Квартира 1</a>
    <a class="a-card__title" href="/a/show/444444444">Квартира 2</a>
  </div>
</body></html>
"""


def test_extract_skips_sidebar_on_empty_search() -> None:
    scraper = KrishaScraper()
    assert scraper._extract_listing_urls(EMPTY_HTML) == []


def test_selectbox_not_found_does_not_hide_results() -> None:
    scraper = KrishaScraper()
    urls = scraper._extract_listing_urls(SELECTBOX_NOT_FOUND_HTML)
    assert urls == ["https://krisha.kz/a/show/333333333"]


def test_extract_reads_card_titles() -> None:
    scraper = KrishaScraper()
    urls = scraper._extract_listing_urls(CARDS_HTML)
    assert urls == [
        "https://krisha.kz/a/show/333333333",
        "https://krisha.kz/a/show/444444444",
    ]
