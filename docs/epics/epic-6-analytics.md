# Epic 6: Аналитика рынка

**Цель:** Накапливать исторические срезы рынка по ЖК и районам, считать скорость продажи и давать стабильную базу для скоринга.  
**Зависимости:** MVP (Epic 1–5)  
**Следующий эпик:** [Epic 7 — Скоринг и рейтинг](epic-7-scoring.md)

> **Контекст:** Сейчас `DealAnalyzer` считает медианы на лету с кэшем в памяти на 30 мин. В V2 статистика сохраняется в БД и обновляется по расписанию.

**Покрывает разделы ТЗ:** §5 (история), §6 (анализ рынка)

---

## Задачи

| # | Задача | Статус |
|---|---|---|
| 6.1 | [Таблица `analytics`](#задача-61--таблица-analytics) | ✅ |
| 6.2 | [Сервис расчёта рыночной статистики](#задача-62--сервис-расчёта-рыночной-статистики) | ✅ |
| 6.3 | [Скорость продажи](#задача-63--скорость-продажи) | ✅ |
| 6.4 | [Джоба пересчёта аналитики](#задача-64--джоба-пересчёта-аналитики) | ✅ |
| 6.5 | [Рефакторинг DealAnalyzer](#задача-65--рефакторинг-dealanalyzer) | ✅ |

---

## Задача 6.1 — Таблица `analytics`

**Описание:** Персистентное хранение срезов рынка по ЖК и районам.

### Чеклист

- [x] `app/models/analytics.py` — модель `MarketAnalytics`
- [x] Alembic-миграция `analytics`
- [x] Индексы: `(complex_id, calculated_at)`, `(district, calculated_at)`
- [x] Модель экспортирована в `app/models/__init__.py`

### Схема

```sql
analytics:
  id
  complex_id          -- FK nullable (NULL = агрегат по району)
  district            -- nullable
  rooms               -- nullable, для срезов по комнатности
  median_price
  avg_price
  median_price_per_sqm
  avg_price_per_sqm
  active_count
  sold_last_30d       -- кол-во снятых за 30 дней
  avg_days_on_market  -- среднее время до снятия
  calculated_at
```

### Курсор-промпт

```
Ты разрабатываешь Python-проект "krisha_monitoring".

**Задача:** Создать модель `MarketAnalytics` и Alembic-миграцию для таблицы `analytics`.

**Требования:**
- SQLAlchemy 2.0 async, типизация Mapped[]
- `complex_id` — FK на `residential_complexes.id`, nullable
- `district` — String, nullable (для районных срезов без привязки к ЖК)
- `rooms` — Integer, nullable
- Цены — BigInteger / Integer
- `avg_days_on_market` — Float, nullable
- `calculated_at` — DateTime(timezone=True), server_default=now()
- Составной индекс (complex_id, calculated_at DESC)

**Создай:**
- `app/models/analytics.py`
- `app/repositories/analytics_repo.py` с методами:
  - `save_snapshot(session, data) -> MarketAnalytics`
  - `get_latest_by_complex(session, complex_id, rooms=None) -> MarketAnalytics | None`
  - `get_latest_by_district(session, district, rooms=None) -> MarketAnalytics | None`
  - `get_history(session, complex_id, days=90) -> list[MarketAnalytics]`

**Не меняй** существующие таблицы без необходимости.
```

---

## Задача 6.2 — Сервис расчёта рыночной статистики

**Описание:** Вынести расчёт медиан/средних из кэша в отдельный сервис с записью в БД.

### Чеклист

- [x] `app/analyzer/market_analytics.py` — класс `MarketAnalyticsService`
- [x] Метод `compute_complex_stats(complex_id, rooms=None) -> MarketStats`
- [x] Метод `compute_district_stats(district, rooms=None) -> MarketStats`
- [x] Минимум 5 активных объявлений для расчёта (как в `DealAnalyzer`)
- [x] Сохранение снимка через `analytics_repo.save_snapshot`
- [x] Unit-тесты на расчёт медиан

### Курсор-промпт

```
Ты разрабатываешь Python-проект "krisha_monitoring".

**Задача:** Создать `app/analyzer/market_analytics.py`.

**Класс `MarketAnalyticsService(session: AsyncSession)`:**

```python
async def compute_and_save_complex(self, complex_id: int, *, rooms: int | None = None) -> MarketAnalytics | None:
    """Посчитать статистику по ЖК и сохранить снимок в analytics."""

async def compute_and_save_all_complexes(self) -> int:
    """Пересчитать все ЖК. Вернуть количество сохранённых снимков."""

async def compute_and_save_districts(self) -> int:
    """Агрегаты по district из активных квартир."""
```

**Логика расчёта:**
- Брать только `is_active=True` и валидные `external_id` (цифры)
- Использовать `statistics.median` / `statistics.mean`
- Если активных < 5 — не сохранять, вернуть None
- Переиспользовать dataclass `MarketStats` из `deal_analyzer.py` или вынести в `app/analyzer/types.py`

**Тесты:** `tests/test_market_analytics.py` — минимум 5 квартир, проверка медианы.
```

---

## Задача 6.3 — Скорость продажи

**Описание:** Рассчитать, как быстро снимаются объявления — по `apartment_status_history` и датам `first_seen_at` / `last_seen_at`.

### Чеклист

- [x] Метод `compute_sale_velocity(complex_id) -> SaleVelocity`
- [x] `sold_last_30d` — объявления, ставшие inactive за 30 дней
- [x] `avg_days_on_market` — среднее `(last_seen_at - first_seen_at)` для снятых
- [x] Поля записываются в снимок `analytics`
- [x] Тесты на fixture-данных status_history

### Метрики

```python
@dataclass
class SaleVelocity:
    sold_last_30d: int
    avg_days_on_market: float | None
    median_days_on_market: float | None
```

### Курсор-промпт

```
Ты разрабатываешь Python-проект "krisha_monitoring".

**Задача:** Добавить расчёт скорости продажи в `MarketAnalyticsService`.

**Источники данных:**
- `apartments`: `is_active=False`, `first_seen_at`, `last_seen_at`
- `apartment_status_history`: status=inactive

**Метрики для каждого ЖК:**
- `sold_last_30d` — сколько объявлений стало неактивными за последние 30 дней
- `avg_days_on_market` — среднее число дней от first_seen_at до момента снятия
- Опционально: медиана дней на рынке

**Интеграция:** при `compute_and_save_complex` записывать `sold_last_30d` и `avg_days_on_market` в таблицу `analytics`.

**Тесты:** создать 3 квартиры с разными датами снятия, проверить avg_days_on_market.
```

---

## Задача 6.4 — Джоба пересчёта аналитики

**Описание:** Периодически обновлять снимки рынка независимо от парсера.

### Чеклист

- [x] `app/scheduler/jobs.py` — `analytics_job()`
- [x] Расписание: 1 раз в сутки (ночь) + опционально после `scrape_job`
- [x] Guard от параллельного запуска (как у `scrape_job`)
- [x] Логирование: сколько ЖК/районов пересчитано
- [x] `GET /scheduler/status` — показать last run analytics

### Курсор-промпт

```
Ты разрабатываешь Python-проект "krisha_monitoring".

**Задача:** Добавить джобу `analytics_job` в планировщик.

**Поведение:**
1. `MarketAnalyticsService.compute_and_save_all_complexes()`
2. `MarketAnalyticsService.compute_and_save_districts()`
3. Лог: "Analytics job done: {n} complex snapshots, {m} district snapshots"

**Расписание:**
- Cron: 03:00 Asia/Almaty ежедневно
- Дополнительно: вызов в конце успешного `scrape_job` (опционально, через флаг в settings)

**Не блокировать** scrape_job — analytics в отдельной asyncio task или после scrape с try/except.
```

---

## Задача 6.5 — Рефакторинг DealAnalyzer

**Описание:** `DealAnalyzer` читает последний снимок из `analytics`, а не пересчитывает каждый раз.

### Чеклист

- [x] `get_market_stats()` — сначала `analytics_repo.get_latest_by_complex`, fallback на live-расчёт
- [x] Убрать или сократить in-memory `_stats_cache` (оставить только как L1 на 5 мин)
- [x] `/discount` и уведомления работают без регрессий
- [x] Обновить тесты `test_deal_analyzer.py`

### Курсор-промпт

```
Ты разрабатываешь Python-проект "krisha_monitoring".

**Задача:** Перевести `DealAnalyzer.get_market_stats` на чтение из таблицы `analytics`.

**Логика:**
1. `analytics_repo.get_latest_by_complex(complex_id)` — если снимок свежее 24ч, использовать его
2. Иначе — live-расчёт по активным квартирам (текущее поведение) + опционально trigger save

**Сохранить обратную совместимость** dataclass `MarketStats` и API `find_deals` / `analyze_all_complexes`.

**Прогнать:** `uv run pytest tests/test_deal_analyzer.py -q`
```

---

## Критерии приёмки эпика

- [x] В БД появляются ежедневные срезы по каждому ЖК с ≥5 активными объявлениями
- [x] Для ЖК доступны `sold_last_30d` и `avg_days_on_market`
- [x] `DealAnalyzer` использует сохранённую аналитику
- [x] Все тесты проходят, ruff/mypy чистые
