# Epic 3: Парсер Krisha.kz

**Цель:** Автоматически собирать объявления с krisha.kz по заданным фильтрам поиска, парсить детали и сохранять в БД.  
**Зависимости:** [Epic 2](epic-2-database.md)  
**Следующий эпик:** [Epic 4 — Планировщик](epic-4-scheduler.md)

---

## Задачи

| # | Задача | Статус |
|---|---|---|
| 3.1 | [Playwright — сбор списка объявлений](#задача-31--playwright--сбор-списка-объявлений) | ✅ |
| 3.2 | [Парсер детальной страницы](#задача-32--парсер-детальной-страницы) | ✅ |
| 3.3 | [Сохранение в БД + дедупликация](#задача-33--сохранение-в-бд--дедупликация) | ✅ |
| 3.4 | [Обнаружение снятых объявлений](#задача-34--обнаружение-снятых-объявлений) | ✅ |

---

## Задача 3.1 — Playwright — сбор списка объявлений

**Описание:** Обойти страницы листинга на krisha.kz по URL с фильтрами и собрать URL всех объявлений.

### Чеклист

- [x] `app/scraper/krisha_scraper.py` — класс `KrishaScraper`
- [x] `app/scraper/filters.py` — `SearchFilters`, `default_search_url()`
- [x] Метод `get_listing_urls(search_url: str) -> list[str]`
- [x] Пагинация — `&page={n}` до отсутствия новых объявлений
- [x] Headless Chromium через Playwright (async)
- [x] Обработка anti-bot: случайные задержки 1–3 сек между запросами
- [x] Логирование количества найденных объявлений
- [x] Повторные попытки при ошибке сети (3 попытки, backoff 5, 10, 20 сек)

### URL-паттерн Krisha.kz

```
https://krisha.kz/prodazha/kvartiry/astana/?_txt_=Срочно&das[live.rooms]=2&...&page={n}
```

Опционально фильтр по ЖК: `das[map.complex]={complex_id}`

---

## Задача 3.2 — Парсер детальной страницы

**Описание:** Открыть страницу объявления и извлечь все данные.

### Чеклист

- [x] `app/scraper/parser.py` — функция `parse_apartment_page(html, url) -> dict`
- [x] Парсинг через BeautifulSoup + lxml
- [x] Извлекать все поля модели `Apartment` + данные продавца
- [x] Нормализация цен и площадей
- [x] Определение типа продавца: owner / agent / agency
- [x] `tests/test_parser.py` + fixture `tests/fixtures/listing_detail.html`

---

## Задача 3.3 — Сохранение в БД + дедупликация

**Описание:** Запустить полный цикл парсинга по URL поиска и сохранить результаты.

### Чеклист

- [x] `app/scraper/scrape_service.py` — класс `ScrapeService`
- [x] Метод `scrape_search(search_url: str) -> ScrapeResult`
- [x] Метод `scrape_all()` — использует `KRISHA_SEARCH_URL` из конфига
- [x] Дедупликация: не парсить детали, если объявление видели < 1 часа назад
- [x] Счётчик: новые / обновлённые / без изменений
- [x] Concurrency: `asyncio.Semaphore(3)` для загрузки страниц
- [x] CLI: `uv run python -m app.scraper`

---

## Задача 3.4 — Обнаружение снятых объявлений

**Описание:** Сравнивать текущий листинг с БД и помечать исчезнувшие объявления.

### Чеклист

- [x] Логика в `apartment_repo.mark_inactive()`
- [x] Запись в `apartment_status_history` со статусом `inactive`
- [x] Защита «2 цикла»: `last_seen_at` старше `2 * parser_interval_minutes`
- [x] Возвращает `list[Apartment]` для уведомлений
- [x] Логирование количества снятых объявлений
- [ ] Уведомление в Telegram при снятии (TODO: Epic 5)

---

## Конфигурация

`.env` / `.env.example`:

```
KRISHA_SEARCH_URL=https://krisha.kz/prodazha/kvartiry/astana/?...
SCRAPER_MAX_LISTINGS=   # опционально, лимит для dev
```
