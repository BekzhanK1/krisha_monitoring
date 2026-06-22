# Epic 3: Парсер Krisha.kz

**Цель:** Автоматически собирать объявления с krisha.kz по заданным ЖК, парсить детали и сохранять в БД.  
**Зависимости:** [Epic 2](epic-2-database.md)  
**Следующий эпик:** [Epic 4 — Планировщик](epic-4-scheduler.md)

---

## Задачи

| # | Задача | Статус |
|---|---|---|
| 3.1 | [Playwright — сбор списка объявлений](#задача-31--playwright--сбор-списка-объявлений) | 🔲 |
| 3.2 | [Парсер детальной страницы](#задача-32--парсер-детальной-страницы) | 🔲 |
| 3.3 | [Сохранение в БД + дедупликация](#задача-33--сохранение-в-бд--дедупликация) | 🔲 |
| 3.4 | [Обнаружение снятых объявлений](#задача-34--обнаружение-снятых-объявлений) | 🔲 |

---

## Задача 3.1 — Playwright — сбор списка объявлений

**Описание:** Обойти страницы листинга ЖК на krisha.kz и собрать URL всех объявлений.

### Чеклист

- [ ] `app/scraper/krisha_scraper.py` — класс `KrishaScraper`
- [ ] Метод `get_listing_urls(complex_name: str) -> list[str]`
- [ ] Пагинация — перебирать страницы до последней
- [ ] Headless Chromium через Playwright (async)
- [ ] Обработка anti-bot: случайные задержки 1–3 сек между запросами
- [ ] Логирование количества найденных объявлений
- [ ] Повторные попытки при ошибке сети (3 попытки, экспоненциальный backoff)

### URL-паттерн Krisha.kz

```
https://krisha.kz/prodazha/kvartiry/astana/?das[complex]={complex_id}&page={n}
```

### Курсор-промпт

```
Ты разрабатываешь Python-проект "krisha_monitoring" — парсер krisha.kz.

**Задача:** Создать `app/scraper/krisha_scraper.py` — сбор URL объявлений.

**Класс `KrishaScraper`:**

```python
class KrishaScraper:
    def __init__(self, headless: bool = True): ...
    async def __aenter__(self): ...  # запуск playwright
    async def __aexit__(self, ...): ...  # закрытие
    async def get_listing_urls(self, complex_name: str, rooms: list[int] = [2, 3]) -> list[str]: ...
```

**Логика `get_listing_urls`:**
1. Открыть страницу листинга krisha.kz с фильтром по ЖК и комнатности
2. Найти все карточки объявлений (CSS-селектор: `a.a-card__title` или аналог)
3. Собрать href ссылок — это URL объявлений
4. Перейти на следующую страницу (кнопка пагинации), повторить
5. Остановиться, когда кнопка "следующая" отсутствует
6. Вернуть deduplicated list[str] с полными URL

**Требования:**
- async playwright с `async with async_playwright()`
- Случайная задержка `asyncio.sleep(random.uniform(1.0, 3.0))` между страницами
- User-Agent: современный Chrome
- Логировать каждую страницу: logger.info(f"Page {n}: found {count} listings")
- При ошибке загрузки страницы — retry 3 раза с задержкой 5, 10, 20 сек
- Не захардкоживать селекторы — вынести в константы вверху файла
```

---

## Задача 3.2 — Парсер детальной страницы

**Описание:** Открыть страницу объявления и извлечь все данные.

### Чеклист

- [ ] `app/scraper/parser.py` — функция `parse_apartment_page(html: str) -> dict`
- [ ] Парсинг через BeautifulSoup
- [ ] Извлекать все 21 поле из ТЗ (раздел 4)
- [ ] Нормализация цен: убрать пробелы, конвертировать в `int`
- [ ] Нормализация площадей: `float`
- [ ] Определение типа продавца: собственник / риелтор / агентство
- [ ] Обработка отсутствующих полей — `None`, не падать

### Маппинг полей

```python
FIELD_MAP = {
    "Этаж": "floor",
    "Этажей в доме": "total_floors",
    "Год постройки": "year_built",
    "Тип дома": "house_type",
    "Высота потолков": "ceiling_height",
    "Состояние": "condition",
    "Балкон": "balcony",
    "Санузел": "bathroom",
}
```

### Курсор-промпт

```
Ты разрабатываешь Python-проект "krisha_monitoring" — парсер krisha.kz.

**Задача:** Создать `app/scraper/parser.py` — парсинг HTML страницы объявления.

**Функция:**
```python
def parse_apartment_page(html: str, url: str) -> dict | None:
    """
    Принимает HTML страницы объявления krisha.kz.
    Возвращает словарь с данными или None если страница невалидна.
    """
```

**Что извлечь:**
- external_id: из URL (число в конце: /123456.html)
- url: переданный url
- price: цена в тенге (int)
- price_per_sqm: цена за м² (int)
- address: полный адрес
- rooms: количество комнат (int)
- total_area, living_area, kitchen_area: float
- floor, total_floors: int
- year_built: int
- house_type, condition, balcony, bathroom: str
- ceiling_height: float
- description: текст описания
- photos: список URL фотографий (list[str])
- seller_name: имя продавца
- seller_phone: телефон продавца
- seller_type: "owner" | "agent" | "agency" (определить по тексту)
- district: район из breadcrumbs или адреса

**Логика определения seller_type:**
- Если в профиле продавца есть слова "агентство", "риэлтор", "realty" → "agency"
- Если есть "агент" → "agent"  
- Иначе → "owner"

**Требования:**
- BeautifulSoup4 с парсером lxml
- Все поля оборачивать в try/except — вернуть None для поля, не для всего объекта
- Функции-хелперы: `_parse_price(text) -> int`, `_parse_area(text) -> float`
- 100% покрытие: если HTML невалидный — вернуть None
- Тесты: создать `tests/test_parser.py` с fixture из реального HTML
```

---

## Задача 3.3 — Сохранение в БД + дедупликация

**Описание:** Запустить полный цикл парсинга для списка ЖК и сохранить результаты.

### Чеклист

- [ ] `app/scraper/scrape_service.py` — класс `ScrapeService`
- [ ] Метод `scrape_complex(complex_name: str)` — полный цикл для одного ЖК
- [ ] Метод `scrape_all()` — перебор всех ЖК из БД
- [ ] Дедупликация: не парсить детали, если объявление видели < 1 часа назад
- [ ] Счётчик: новые / обновлённые / без изменений
- [ ] Логирование итогов каждого ЖК

### Курсор-промпт

```
Ты разрабатываешь Python-проект "krisha_monitoring".

**Задача:** Создать `app/scraper/scrape_service.py` — оркестратор парсинга.

**Класс `ScrapeService`:**

```python
class ScrapeService:
    def __init__(self, session: AsyncSession): ...
    
    async def scrape_complex(self, complex_name: str) -> ScrapeResult: ...
    async def scrape_all(self) -> list[ScrapeResult]: ...
```

**Dataclass `ScrapeResult`:**
```python
@dataclass
class ScrapeResult:
    complex_name: str
    total_found: int
    new: int
    updated: int
    unchanged: int
    errors: int
    duration_sec: float
```

**Логика `scrape_complex`:**
1. Получить `complex_id` через `complex_repo.get_or_create()`
2. Через `KrishaScraper` получить все URL листинга
3. Для каждого URL:
   a. Проверить: если `apartment.last_seen_at` < 1 часа назад — пропустить (only update timestamp)
   b. Загрузить HTML страницы через Playwright
   c. `parse_apartment_page(html, url)`
   d. `apartment_repo.upsert_apartment(session, data)`
4. `apartment_repo.mark_inactive()` для снятых объявлений
5. Зафиксировать `session.commit()`
6. Вернуть `ScrapeResult`

**Требования:**
- Concurrency: обрабатывать не более 3 страниц одновременно (asyncio.Semaphore(3))
- Каждую ошибку парсинга — логировать и продолжать, не останавливать весь цикл
- Время выполнения фиксировать через time.monotonic()
```

---

## Задача 3.4 — Обнаружение снятых объявлений

**Описание:** Сравнивать текущий листинг с БД и помечать исчезнувшие объявления.

### Чеклист

- [ ] Логика встроена в `apartment_repo.mark_inactive()`
- [ ] При снятии объявления — запись в `apartment_status_history` со статусом `inactive`
- [ ] Поле `apartments.last_seen_at` обновляется при каждом парсинге
- [ ] Объявление считается снятым, если его нет в листинге 2 цикла подряд
- [ ] Уведомление в Telegram при снятии объявления из вотчлиста (TODO: связать с Epic 5)

### Курсор-промпт

```
Ты разрабатываешь Python-проект "krisha_monitoring".

**Задача:** Улучшить `mark_inactive` в `app/repositories/apartment_repo.py`.

**Текущая логика:**
- Получить все external_id с текущего листинга
- Пометить is_active=False у тех, которых нет в списке

**Добавить:**
1. Логику "2 цикла подряд": объявление снимается, только если `last_seen_at` 
   старше чем `2 * parser_interval_minutes`
   (защита от временных сбоев парсинга)

2. При каждом `mark_inactive` — вставить запись в `apartment_status_history`:
   ```python
   ApartmentStatusHistory(
       apartment_id=apt.id,
       status="inactive",
       changed_at=datetime.now(UTC)
   )
   ```

3. Логировать: `logger.info(f"Marked {count} apartments as inactive in {complex_name}")`

4. Возвращать список `Apartment` объектов (не только count), чтобы можно было 
   отправить уведомления в Telegram (Epic 5)

**Файл:** `app/repositories/apartment_repo.py`
```
