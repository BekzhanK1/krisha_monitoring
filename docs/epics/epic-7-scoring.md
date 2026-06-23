# Epic 7: Скоринг и инвестиционный рейтинг

**Цель:** Оценивать каждую квартиру по инвестиционной привлекательности, считать ROI сделки и вероятность собственника.  
**Зависимости:** [Epic 6 — Аналитика](epic-6-analytics.md)  
**Следующий эпик:** [Epic 8 — Telegram V2 и охотник](epic-8-telegram-v2.md)

**Покрывает разделы ТЗ:** §9 (продавцы), §11 (рейтинг), §12 (финансы)

---

## Задачи

| # | Задача | Статус |
|---|---|---|
| 7.1 | [Вероятность собственника](#задача-71--вероятность-собственника) | ✅ |
| 7.2 | [Инвестиционный рейтинг A+–D](#задача-72--инвестиционный-рейтинг-ad) | ✅ |
| 7.3 | [Финансовая модель сделки](#задача-73--финансовая-модель-сделки) | ✅ |
| 7.4 | [Таблица `apartment_scores`](#задача-74--таблица-apartment_scores) | ✅ |
| 7.5 | [Интеграция в DealAnalyzer](#задача-75--интеграция-в-dealanalyzer) | ✅ |

---

## Задача 7.1 — Вероятность собственника

**Описание:** Заполнять `sellers.owner_probability` на основе типа продавца и эвристик из парсера.

### Чеклист

- [x] `app/analyzer/seller_scorer.py` — `estimate_owner_probability(seller, description) -> float`
- [x] Обновление `owner_probability` при scrape в `_upsert_seller`
- [x] Эвристики: owner → 0.85, agent → 0.25, agency → 0.10
- [x] Бонусы: «от собственника» в тексте +0.1, «агентство» −0.15
- [x] Тесты на комбинации типов и текста

### Курсор-промпт

```
Ты разрабатываешь Python-проект "krisha_monitoring".

**Задача:** Создать `app/analyzer/seller_scorer.py`.

```python
def estimate_owner_probability(
    *,
    seller_type: SellerType | None,
    description: str | None,
    seller_name: str | None = None,
) -> float:
    """Вернуть вероятность 0.0–1.0 что продавец — собственник."""
```

**Правила (настраиваемые константы):**
- `SellerType.OWNER` → база 0.85
- `SellerType.AGENT` → 0.25
- `SellerType.AGENCY` → 0.10
- Ключевые слова в description: «собственник», «хозяин» → +0.10; «риелтор», «агентство» → −0.15
- Clamp 0.0–1.0

**Интеграция:** в `scrape_service._upsert_seller` записывать `owner_probability`.

**Тесты:** `tests/test_seller_scorer.py`
```

---

## Задача 7.2 — Инвестиционный рейтинг A+–D

**Описание:** Правило-based скоринг до появления ML-моделей (V3).

### Чеклист

- [x] `app/analyzer/investment_scorer.py` — класс `InvestmentScorer`
- [x] Enum `InvestmentGrade`: A_PLUS, A, B, C, D
- [x] Метод `score(apartment, market_stats, deal_signals) -> ScoredApartment`
- [x] Веса: дисконт, мотивация, owner_probability, скорость продажи ЖК, этаж/год
- [x] Документация порогов в docstring

### Шкала (черновик)

| Балл | Рейтинг | Условия (пример) |
|---|---|---|
| ≥85 | A+ | дисконт ≥15%, мотивация, owner ≥0.7, ТОП-3 по цене/м² |
| ≥70 | A | дисконт ≥10%, хотя бы 2 сигнала сделки |
| ≥55 | B | дисконт ≥5% или ТОП-5 |
| ≥40 | C | на рынке, без явного дисконта |
| <40 | D | выше медианы или слабый ЖК |

### Курсор-промпт

```
Ты разрабатываешь Python-проект "krisha_monitoring".

**Задача:** Создать `app/analyzer/investment_scorer.py` — rule-based рейтинг.

**Dataclasses:**

```python
class InvestmentGrade(StrEnum):
    A_PLUS = "A+"
    A = "A"
    B = "B"
    C = "C"
    D = "D"

@dataclass
class ScoredApartment:
    apartment_id: int
    grade: InvestmentGrade
    score: float          # 0–100
    discount_pct: float
    reasons: list[str]    # человекочитаемые факторы
```

**Входные данные:**
- `Apartment`
- `MarketStats` (из analytics или DealAnalyzer)
- `Deal` signals: discount_pct, is_motivated_seller, owner_probability
- Опционально: `SaleVelocity` из analytics

**Метод:**
```python
def score(self, apartment, market_stats, *, deal: Deal | None = None, owner_probability: float | None = None) -> ScoredApartment
```

**Требования:**
- Пороги вынести в константы в начале файла
- Unit-тесты: квартира с −12% и «срочно» → минимум A
- Без внешних ML-зависимостей
```

---

## Задача 7.3 — Финансовая модель сделки

**Описание:** Расчёт ROI с учётом покупки, ремонта, налогов и ожидаемой продажи.

### Чеклист

- [x] `app/analyzer/financial_model.py` — `DealFinancials`
- [x] Параметры по умолчанию в `app/config.py` или отдельный `InvestmentSettings`
- [x] `expected_sale_price` — медиана ЖК или fair value из market_stats
- [x] Поля: purchase_price, renovation_cost, taxes, total_cost, profit, roi_pct
- [x] Тесты на типовую 2-комнатную сделку

### Формула (упрощённая V2)

```
total_cost = price + renovation + notary + agency_fee (если покупатель платит)
profit     = expected_sale_price - total_cost - capital_gains_tax
roi_pct    = profit / total_cost * 100
```

### Курсор-промпт

```
Ты разрабатываешь Python-проект "krisha_monitoring".

**Задача:** Создать `app/analyzer/financial_model.py`.

```python
@dataclass
class DealFinancials:
    purchase_price: int
    renovation_cost: int
    transaction_costs: int
    expected_sale_price: int
    capital_gains_tax: int
    total_cost: int
    profit: int
    roi_pct: float

def calculate_deal_financials(
    apartment: Apartment,
    market_stats: MarketStats,
    *,
    renovation_per_sqm: int = 150_000,
    transaction_fee_pct: float = 0.01,
    capital_gains_tax_pct: float = 0.10,
) -> DealFinancials:
```

**Логика:**
- `expected_sale_price` = `market_stats.median_price` (или median_price_per_sqm * area)
- `renovation_cost` = renovation_per_sqm * total_area (если condition плохое — ×1.5)
- Налог только если profit > 0

**Добавь в Settings** (pydantic): `renovation_per_sqm`, `transaction_fee_pct` — с разумными дефолтами.

**Тесты:** цена 25M, медиана 30M → profit > 0, roi_pct > 0
```

---

## Задача 7.4 — Таблица `apartment_scores`

**Описание:** Хранить последний скор и ROI по каждой активной квартире.

### Чеклист

- [x] `app/models/apartment_score.py` — модель `ApartmentScore`
- [x] Alembic-миграция
- [x] `app/repositories/score_repo.py` — upsert по `apartment_id`
- [x] Уникальный индекс на `apartment_id`
- [x] Поля: grade, score, discount_pct, roi_pct, owner_probability, calculated_at
- [x] `app/analyzer/scoring_service.py` — `score_apartment`, `score_all_active`
- [x] `scoring_job()` в `app/scheduler/jobs.py` (cron 04:00, после analytics опционально)
- [x] Тесты `tests/test_scoring_service.py`, `tests/test_score_repo.py`, `tests/test_scoring_job.py`

### Схема

```sql
apartment_scores:
  id
  apartment_id        -- FK unique
  grade               -- A+, A, B, C, D
  score               -- float 0–100
  discount_pct
  roi_pct
  owner_probability
  recommendation      -- text, краткая рекомендация
  calculated_at
```

### Курсор-промпт

```
Ты разрабатываешь Python-проект "krisha_monitoring".

**Задача:** Модель `ApartmentScore`, репозиторий и джоба пересчёта.

**`score_repo.upsert_score(session, apartment_id, data)`** — insert or update.

**Джоба `scoring_job`** (в `app/scheduler/jobs.py`):
- Для каждой активной квартиры с валидным external_id
- Получить market_stats + owner_probability
- `InvestmentScorer.score()` + `calculate_deal_financials()`
- Сохранить в `apartment_scores` с `recommendation` (1–2 предложения на русском)

**Запуск:** после `analytics_job` или раз в сутки.
```

---

## Задача 7.5 — Интеграция в DealAnalyzer

**Описание:** Обогатить `Deal` рейтингом, ROI и текстом рекомендации.

### Чеклист

- [x] Расширить dataclass `Deal`: `grade`, `score`, `roi_pct`, `recommendation`
- [x] `find_deals` подтягивает данные из `apartment_scores` если есть
- [x] Уведомления и `/discount` показывают рейтинг и ROI
- [x] Сортировка deals: сначала по grade/score, потом discount_pct

### Курсор-промпт

```
Ты разрабатываешь Python-проект "krisha_monitoring".

**Задача:** Интегрировать скоринг в DealAnalyzer и Telegram.

**DealAnalyzer:**
- При формировании `Deal` читать `apartment_scores` для apartment_id
- Если скора нет — вычислить on-the-fly через InvestmentScorer (без записи в БД)

**Уведомления (`app/telegram/notifications.py`):**
- Добавить в карточку: `⭐ A | ROI 12% | Рекомендация: ...`

**Handlers `/discount`:**
- Показывать grade и roi_pct в карточке

**Не ломать** существующие тесты; обновить fixtures при необходимости.
```

---

## Критерии приёмки эпика

- [ ] У каждого активного объявления может быть запись в `apartment_scores`
- [x] `/discount` показывает рейтинг A+–D и ROI
- [ ] `sellers.owner_probability` заполняется при парсинге
- [ ] Rule-based скоринг покрыт тестами без ML-зависимостей
