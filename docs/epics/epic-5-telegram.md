# Epic 5: Telegram Bot

**Цель:** Уведомлять о выгодных квартирах и обрабатывать команды пользователя через Telegram.  
**Зависимости:** [Epic 4](epic-4-scheduler.md)  
**Следующий эпик:** Версия 2 (Аналитика)

---

## Задачи

| # | Задача | Статус |
|---|---|---|
| 5.1 | [Настройка бота](#задача-51--настройка-бота) | 🔲 |
| 5.2 | [Анализатор выгодных сделок](#задача-52--анализатор-выгодных-сделок) | 🔲 |
| 5.3 | [Автоматические уведомления](#задача-53--автоматические-уведомления) | 🔲 |
| 5.4 | [Команды бота /top, /new, /discount](#задача-54--команды-бота-top-new-discount) | 🔲 |

---

## Задача 5.1 — Настройка бота

**Описание:** Инициализировать `python-telegram-bot`, запускать в lifespan FastAPI.

### Чеклист

- [ ] `app/telegram/bot.py` — создание `Application` и `Bot`
- [ ] Бот запускается в lifespan (polling или webhook)
- [ ] `app/telegram/sender.py` — функция `send_message(text, parse_mode="HTML")`
- [ ] Обработка ошибок отправки (retry 3 раза)
- [ ] Логирование каждой отправки

### Курсор-промпт

```
Ты разрабатываешь Python-проект "krisha_monitoring".

**Задача:** Настроить Telegram бота через python-telegram-bot v21+.

**Создай `app/telegram/bot.py`:**

```python
from telegram.ext import Application, CommandHandler

def create_application() -> Application:
    app = Application.builder().token(settings.telegram_bot_token).build()
    # регистрация handlers
    return app
```

**Создай `app/telegram/sender.py`:**

```python
async def send_alert(text: str, chat_id: int | None = None) -> bool:
    """Отправить сообщение. Возвращает True при успехе."""
```

- chat_id по умолчанию берётся из settings.telegram_chat_id
- Форматирование: HTML parse_mode
- Retry: 3 попытки с задержкой 2, 4, 8 сек при ошибке
- Логировать успех/ошибку

**Интеграция в `app/main.py` lifespan:**
- Запуск: `await application.initialize()` + `await application.start()`
- Запуск polling в фоне: `asyncio.create_task(application.updater.start_polling())`
- Остановка: `await application.stop()` + `await application.shutdown()`

**Требования:**
- Бот должен отвечать на команду /start текстом "Krisha Monitor запущен"
- Не использовать `run_polling()` — он блокирующий
- Обрабатывать `telegram.error.Forbidden` (бот заблокирован пользователем)
```

---

## Задача 5.2 — Анализатор выгодных сделок

**Описание:** Логика поиска квартир ниже рынка согласно критериям из ТЗ.

### Чеклист

- [ ] `app/analyzer/deal_analyzer.py` — класс `DealAnalyzer`
- [ ] Метод `get_market_stats(complex_id) -> MarketStats` — средняя/медианная цена
- [ ] Метод `find_deals(complex_id) -> list[Deal]` — квартиры с дисконтом
- [ ] Критерии из ТЗ: цена ниже медианы на 10%, цена/м² ниже на 10%, ТОП-5
- [ ] Расчёт `discount_pct` — процент дисконта от медианы
- [ ] Определение мотивированных продавцов по тексту описания

### Критерии

```python
# Квартира считается выгодной если выполняется хотя бы одно:
is_deal = (
    apartment.price < market_stats.median_price * 0.9
    or apartment.price_per_sqm < market_stats.median_price_per_sqm * 0.9
    or apartment in top_5_cheapest(complex_id)
)
```

### Курсор-промпт

```
Ты разрабатываешь Python-проект "krisha_monitoring".

**Задача:** Создать `app/analyzer/deal_analyzer.py` — поиск выгодных квартир.

**Dataclasses:**

```python
@dataclass
class MarketStats:
    complex_id: int
    complex_name: str
    median_price: int
    avg_price: int
    median_price_per_sqm: int
    avg_price_per_sqm: int
    active_count: int
    calculated_at: datetime

@dataclass
class Deal:
    apartment: Apartment
    market_stats: MarketStats
    discount_pct: float  # процент ниже медианы
    deal_reasons: list[str]  # почему считается выгодной
    is_motivated_seller: bool
    motivation_signs: list[str]  # "срочно", "торг", etc.
```

**Класс `DealAnalyzer`:**

```python
class DealAnalyzer:
    def __init__(self, session: AsyncSession): ...
    
    async def get_market_stats(self, complex_id: int) -> MarketStats: ...
    async def find_deals(self, complex_id: int) -> list[Deal]: ...
    async def analyze_all_complexes(self) -> list[Deal]: ...
```

**Логика `find_deals`:**
1. Получить все активные квартиры ЖК
2. Вычислить MedianPrice и AvgPrice (statistics.median/mean)
3. Найти квартиры по критериям из ТЗ (цена -10%, цена/м² -10%, ТОП-5)
4. Для каждой — определить мотивированных продавцов:
   Слова в описании: "срочно", "торг", "переезд", "ипотека", "снижение"
5. Вернуть список Deal, отсортированный по discount_pct DESC

**Требования:**
- Минимум 5 активных квартир в ЖК для расчёта статистики (иначе пропустить)
- Кэшировать MarketStats на 30 минут (functools.lru_cache или словарь с timestamp)
- Типизация: все методы аннотированы
```

---

## Задача 5.3 — Автоматические уведомления

**Описание:** После каждого цикла парсинга — отправлять уведомления о новых выгодных квартирах.

### Чеклист

- [ ] Интеграция `DealAnalyzer` в `scrape_job`
- [ ] Отправлять уведомление только для **новых** выгодных квартир (не повторять)
- [ ] Поле `notifications` в БД — фиксировать отправленные уведомления
- [ ] Формат сообщения из ТЗ (раздел 8)
- [ ] Не отправлять дубли: проверять `notifications` перед отправкой

### Формат сообщения

```
🏢 <b>ЖК Название</b>

💰 <b>85 000 000 ₸</b> (-14% от рынка)
📐 75 м² | 3 комн | 5/16 эт
📍 Есиль, ул. Мәңгілік Ел

🏷 Дисконт: 14% ниже медианы
⚡️ Признаки: срочно, торг

🔗 <a href="https://krisha.kz/...">Смотреть объявление</a>
```

### Курсор-промпт

```
Ты разрабатываешь Python-проект "krisha_monitoring".

**Задача:** Интегрировать уведомления в цикл парсинга.

**Создай `app/telegram/notifications.py`:**

```python
async def notify_new_deals(
    deals: list[Deal], 
    session: AsyncSession,
    sender_fn=send_alert
) -> int:
    """
    Отправить уведомления о новых выгодных квартирах.
    Возвращает количество отправленных уведомлений.
    """
```

**Логика:**
1. Для каждой Deal проверить: есть ли запись в `notifications` для этой квартиры
   с типом "deal_alert" за последние 24 часа → если есть, пропустить
2. Сформировать HTML-сообщение по шаблону из ТЗ
3. `await send_alert(message)`
4. Записать в `notifications`: apartment_id, "deal_alert", sent_at, is_sent=True
5. Вернуть count

**Шаблон сообщения (Jinja2 или f-string):**
- ЖК, цена с форматированием (1 000 000 ₸), процент дисконта
- Площадь / комнаты / этаж
- Адрес
- Признаки мотивированного продавца (если есть)
- Ссылка

**Подключить в `app/scheduler/jobs.py`:**
После `scrape_all()` вызвать:
```python
deals = await analyzer.analyze_all_complexes()
sent = await notify_new_deals(deals, session)
logger.info(f"Sent {sent} deal notifications")
```

**Требования:**
- Не дублировать уведомления (проверка через notifications таблицу)
- Если отправка не удалась — записать is_sent=False, не упасть
- Форматирование цены: `f"{price:,}".replace(",", " ")` → "85 000 000"
```

---

## Задача 5.4 — Команды бота /top, /new, /discount

**Описание:** Реализовать команды Telegram-бота для запроса данных.

### Чеклист

- [ ] `/top` — ТОП-10 самых дешёвых квартир по цене/м² прямо сейчас
- [ ] `/new` — квартиры, найденные за последние 24 часа
- [ ] `/discount` — квартиры с дисконтом >10% от медианы
- [ ] Ответ: список карточек, максимум 5 объявлений в одном сообщении
- [ ] Если нет данных — понятный текст "Пока нет данных"
- [ ] Обработка ошибок — не падать, отвечать "Ошибка, попробуйте позже"

### Курсор-промпт

```
Ты разрабатываешь Python-проект "krisha_monitoring".

**Задача:** Создать `app/telegram/handlers.py` — handlers для команд бота.

**Handlers:**

```python
async def cmd_top(update: Update, context: ContextTypes.DEFAULT_TYPE): ...
async def cmd_new(update: Update, context: ContextTypes.DEFAULT_TYPE): ...
async def cmd_discount(update: Update, context: ContextTypes.DEFAULT_TYPE): ...
```

**Логика каждого handler:**
1. Создать async session из sessionmaker
2. Выполнить запрос к БД
3. Сформировать ответное сообщение
4. `await update.message.reply_text(text, parse_mode="HTML")`

**Запросы:**

`/top` → SELECT * FROM apartments WHERE is_active=True 
         ORDER BY price_per_sqm ASC LIMIT 10

`/new` → SELECT * FROM apartments WHERE is_active=True 
         AND first_seen_at > NOW() - INTERVAL '24 hours'
         ORDER BY first_seen_at DESC LIMIT 10

`/discount` → join с market_stats, вернуть квартиры с дисконтом >10%
              (использовать DealAnalyzer.analyze_all_complexes())

**Формат карточки (краткий):**
```
🏢 ЖК | 💰 85 млн (-12%) | 75м² | 5/16 | /kvartira_123
```

**Зарегистрировать в `app/telegram/bot.py`:**
```python
app.add_handler(CommandHandler("top", cmd_top))
app.add_handler(CommandHandler("new", cmd_new))
app.add_handler(CommandHandler("discount", cmd_discount))
```

**Требования:**
- Каждый handler в try/except — при ошибке ответить "⚠️ Произошла ошибка"
- Ограничение: не более 5 объектов в ответе (Telegram ограничивает длину)
- Session закрывается после каждого запроса
- Логировать: какую команду запросил какой user_id
```
