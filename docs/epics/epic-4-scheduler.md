# Epic 4: Планировщик (APScheduler)

**Цель:** Запустить автоматический цикл парсинга каждые 30–60 минут через APScheduler, интегрированный с FastAPI.  
**Зависимости:** [Epic 3](epic-3-parser.md)  
**Следующий эпик:** [Epic 5 — Telegram Bot](epic-5-telegram.md)

---

## Задачи

| # | Задача | Статус |
|---|---|---|
| 4.1 | [Интеграция APScheduler с FastAPI](#задача-41--интеграция-apscheduler-с-fastapi) | ✅ |
| 4.2 | [Job — полный цикл парсинга](#задача-42--job--полный-цикл-парсинга) | ✅ |

---

## Задача 4.1 — Интеграция APScheduler с FastAPI

**Описание:** Настроить `AsyncIOScheduler` и запускать его в lifespan FastAPI.

### Чеклист

- [x] `app/scheduler/scheduler.py` — создание и настройка планировщика
- [x] Планировщик стартует в `lifespan` FastAPI (не в `@app.on_event`)
- [x] При завершении приложения — корректный shutdown планировщика
- [x] Job store: memory (для MVP, без персистентности)
- [x] Endpoint GET `/scheduler/status` — список задач и время следующего запуска

### Курсор-промпт

```
Ты разрабатываешь Python-проект "krisha_monitoring".

**Задача:** Интегрировать APScheduler с FastAPI через lifespan.

**Создай `app/scheduler/scheduler.py`:**

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler(timezone="Asia/Almaty")

def get_scheduler() -> AsyncIOScheduler:
    return scheduler
```

**Обнови `app/main.py`:**

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    scheduler.start()
    # добавить jobs здесь
    yield
    scheduler.shutdown(wait=False)
```

**Добавь endpoint в `app/main.py`:**

```
GET /scheduler/status
→ {
    "running": bool,
    "jobs": [{"id": str, "next_run": str, "trigger": str}]
  }
```

**Требования:**
- timezone: "Asia/Almaty" (UTC+5)
- Логировать старт и остановку планировщика
- Ошибки внутри job не должны останавливать планировщик
  (misfire_grace_time=60, coalesce=True)
```

---

## Задача 4.2 — Job — полный цикл парсинга

**Описание:** Создать APScheduler job, который запускает `ScrapeService.scrape_all()` по расписанию.

### Чеклист

- [x] `app/scheduler/jobs.py` — функция `scrape_job()`
- [x] Job регистрируется в планировщике с интервалом из конфига
- [x] Защита от параллельного запуска (если предыдущий ещё идёт — пропустить)
- [x] Логирование старта, итогов и ошибок каждого цикла
- [x] Результат `ScrapeResult` логируется в структурированном виде

### Курсор-промпт

```
Ты разрабатываешь Python-проект "krisha_monitoring".

**Задача:** Создать `app/scheduler/jobs.py` — job для парсинга.

**Функция `scrape_job()`:**

```python
_is_running = False  # защита от параллельного запуска

async def scrape_job():
    global _is_running
    if _is_running:
        logger.warning("Scrape job already running, skipping")
        return
    _is_running = True
    try:
        # создать async session
        # запустить ScrapeService.scrape_all()
        # логировать результаты
    finally:
        _is_running = False
```

**Зарегистрировать job в `app/scheduler/scheduler.py`:**

```python
from apscheduler.triggers.interval import IntervalTrigger

scheduler.add_job(
    scrape_job,
    trigger=IntervalTrigger(minutes=settings.parser_interval_minutes),
    id="scrape_all",
    replace_existing=True,
    misfire_grace_time=60,
    coalesce=True,
)
```

**Логирование итогов:**
```python
for result in results:
    logger.info(
        "Scrape complete",
        complex=result.complex_name,
        new=result.new,
        updated=result.updated,
        errors=result.errors,
        duration=f"{result.duration_sec:.1f}s"
    )
```

**Требования:**
- Session создаётся и закрывается внутри job (не использовать глобальную)
- Любая необработанная ошибка — логировать с traceback, не поднимать выше
- После первого успешного запуска — логировать "Scraper initialized"
```
