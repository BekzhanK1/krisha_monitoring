# Epic 8: Telegram V2 и «охотник за срочными»

**Цель:** Расширить бота командами из ТЗ, мгновенными алертами по горячим сделкам и редактированием фильтров поиска.  
**Зависимости:** [Epic 7 — Скоринг](epic-7-scoring.md)  
**Следующий этап:** Версия 3 (AI-модели) — отдельные эпики

**Покрывает разделы ТЗ:** §8 (уведомления + рекомендация), §15 (команды), §16 (охотник)

---

## Задачи

| # | Задача | Статус |
|---|---|---|
| 8.1 | [Команда `/zhk`](#задача-81--команда-zhk) | 🔲 |
| 8.2 | [Команда `/report`](#задача-82--команда-report) | 🔲 |
| 8.3 | [Команда `/vip`](#задача-83--команда-vip) | 🔲 |
| 8.4 | [Охотник — мгновенные алерты](#задача-84--охотник--мгновенные-алерты) | 🔲 |
| 8.5 | [Редактирование фильтров в Telegram](#задача-85--редактирование-фильтров-в-telegram) | 🔲 |
| 8.6 | [Улучшенные уведомления](#задача-86--улучшенные-уведомления) | 🔲 |

---

## Задача 8.1 — Команда `/zhk`

**Описание:** Статистика по жилому комплексу из таблицы `analytics`.

### Чеклист

- [ ] Handler `cmd_zhk` — аргумент: название или id ЖК
- [ ] Без аргумента — список ЖК с активными объявлениями (топ-10 по количеству)
- [ ] С аргументом — последний снимок: медиана, средняя, активных, продано за 30д, дней на рынке
- [ ] Формат HTML, компактный блок

### Пример ответа

```
🏢 EXPO Residence
💰 Медиана: 28 млн | 580k/м²
📊 Активных: 42 | Продано за 30д: 8
⏱ Среднее на рынке: 45 дней
```

### Курсор-промпт

```
Ты разрабатываешь Python-проект "krisha_monitoring".

**Задача:** Добавить команду `/zhk` в Telegram bot.

**`/zhk`** — список ЖК (name + active_count из последнего analytics или live count)
**`/zhk EXPO`** — поиск ЖК по ILIKE name, показать MarketAnalytics + SaleVelocity

**Файлы:** `handlers.py`, `bot.py`, тест `tests/test_telegram_handlers.py` с mock session.

**Ограничение:** 1 ЖК в ответе; если несколько совпадений — попросить уточнить.
```

---

## Задача 8.2 — Команда `/report`

**Описание:** Сводный отчёт по рынку за период.

### Чеклист

- [ ] Handler `cmd_report`
- [ ] Данные: новых за 7д, снято за 7д, топ-3 ЖК по дисконту, топ-3 по ликвидности (sold_last_30d)
- [ ] Опционально: `/report 7` / `/report 30` — период в днях
- [ ] Генерация текста в `app/analyzer/report_builder.py`

### Курсор-промпт

```
Ты разрабатываешь Python-проект "krisha_monitoring".

**Задача:** Создать `app/analyzer/report_builder.py` и команду `/report`.

```python
async def build_market_report(session, *, days: int = 7) -> str:
    """Вернуть HTML-текст отчёта для Telegram."""
```

**Секции отчёта:**
1. Заголовок с датой и периодом
2. Новые объявления (count, avg price)
3. Снятые объявления (count)
4. ТОП-3 ЖК по количеству продаж за период
5. ТОП-3 квартиры по grade из apartment_scores (если Epic 7 готов)

**Handler:** parse args из `context.args`, default days=7.
```

---

## Задача 8.3 — Команда `/vip`

**Описание:** Лучшие инвестиционные объекты — grade A+ и A с учётом фильтра `search_configs`.

### Чеклист

- [ ] Handler `cmd_vip`
- [ ] JOIN `apartments` + `apartment_scores` + фильтр `apply_search_filters`
- [ ] Сортировка: grade (A+ first), score DESC, discount_pct DESC
- [ ] Лимит 5 карточек
- [ ] Показать: ЖК, цена, дисконт, grade, ROI, ссылка

### Курсор-промпт

```
Ты разрабатываешь Python-проект "krisha_monitoring".

**Задача:** Команда `/vip` — топ инвестиционных объектов.

**Запрос:**
- Активные квартиры с grade IN ('A+', 'A')
- Применить SearchFilters из активного search_config (как /filter)
- Сортировка: A+ > A, затем score DESC

**Переиспользовать:** `_build_cards`, `_format_apartment_card` — расширить для grade/roi.

**Если apartment_scores пуста:** fallback на DealAnalyzer.analyze_all_complexes() с grade on-the-fly.
```

---

## Задача 8.4 — Охотник — мгновенные алерты

**Описание:** Отдельный быстрый цикл для срочных объявлений ниже рынка (ТЗ §16).

### Чеклист

- [ ] `app/scheduler/hunter_job.py` — логика охотника
- [ ] Интервал: 30 мин (настраивается `HUNTER_INTERVAL_MINUTES`)
- [ ] Условия алерта: новое за последний цикл + (мотивация ИЛИ grade ≥ A) + дисконт ≥ 10%
- [ ] Дедупликация через `notifications` (не слать повторно по apartment_id)
- [ ] Отдельный тип уведомления `hunter_alert`
- [ ] Не дублировать обычные post-scrape уведомления

### Курсор-промпт

```
Ты разрабатываешь Python-проект "krisha_monitoring".

**Задача:** Реализовать «охотника за срочными продажами».

**Новый job `hunter_job`:**
1. Взять квартиры с `first_seen_at` > now - HUNTER_INTERVAL_MINUTES
2. Применить search_filters из active config
3. Для каждой — проверить Deal + grade + motivation
4. Если подходит и нет записи в notifications(type='hunter_alert') — send_alert

**Settings:** `HUNTER_INTERVAL_MINUTES: int = 30` в config.py

**Scheduler:** отдельный IntervalTrigger, не блокирует scrape_job.

**Тесты:** mock send_alert, проверить что повтор не шлётся.
```

---

## Задача 8.5 — Редактирование фильтров в Telegram

**Описание:** Менять `search_configs` без SQL — через бота.

### Чеклист

- [ ] `/settings` — inline-кнопки: «Цена до», «Комнаты», «Площадь», «Текст»
- [ ] ConversationHandler или callback query flow
- [ ] Валидация ввода (числа, диапазоны)
- [ ] `search_config_repo.update_field(config_id, field, value)`
- [ ] Подтверждение после сохранения + превью URL-параметров

### Курсор-промпт

```
Ты разрабатываешь Python-проект "krisha_monitoring".

**Задача:** Редактирование search_configs через Telegram.

**Flow:**
1. `/settings` показывает текущие значения + InlineKeyboard
2. Callback `edit:price_to` → бот просит ввести число
3. MessageHandler ловит ответ → validate → update DB → reply OK

**Использовать:** ConversationHandler или context.user_data для state machine.

**Поля для редактирования (MVP UI):** price_to, rooms, area_from, area_to, text

**Безопасность:** только TELEGRAM_CHAT_ID из settings может редактировать (проверка user/chat id).

**Тесты:** unit-тесты на валидацию, без реального Telegram API.
```

---

## Задача 8.6 — Улучшенные уведомления

**Описание:** Формат из ТЗ §8 с рекомендацией (rule-based, не AI).

### Чеклист

- [ ] Шаблон: ЖК, цена, площадь, дисконт, ссылка, рекомендация
- [ ] `recommendation` из `apartment_scores` или генерация в `InvestmentScorer`
- [ ] Разные шаблоны: `new_deal`, `hunter_alert`, `price_drop`
- [ ] Запись в `notifications` с полным текстом

### Формат (ТЗ)

```
ЖК: EXPO Residence
Цена: 24.5 млн (-14%)
Площадь: 52 м²
Рейтинг: A
ROI: ~11%
Ссылка: ...
Рекомендация: Срочная продажа ниже медианы ЖК, высокая вероятность собственника.
```

### Курсор-промпт

```
Ты разрабатываешь Python-проект "krisha_monitoring".

**Задача:** Обновить `app/telegram/notifications.py` под полный формат ТЗ.

**Функции:**
- `format_deal_alert(deal, financials, scored) -> str`
- `format_hunter_alert(...) -> str`

**Интеграция:** `notify_new_deals()` и `hunter_job` используют новые форматтеры.

**Сохранять** в notifications.message полный текст для истории.
```

---

## Критерии приёмки эпика

- [ ] Работают команды `/zhk`, `/report`, `/vip` из ТЗ
- [ ] Охотник шлёт алерт в течение 30 мин после появления горячей квартиры
- [ ] Фильтры можно менять через `/settings` без правки БД вручную
- [ ] Уведомления содержат рейтинг, ROI и текст рекомендации
- [ ] `/start` обновлён со списком всех команд

---

## Уже реализовано вне эпика (не дублировать)

| Команда | Статус |
|---|---|
| `/filter` | ✅ по search_configs |
| `/fnew` | ✅ новые за 24ч по фильтру |
| `/top`, `/new`, `/discount`, `/settings` | ✅ MVP |

При реализации Epic 8 обновить `/start` и этот epic-файл.
