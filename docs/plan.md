# План разработки — MVP

**Проект:** Krisha Monitoring  
**Этап:** MVP (Парсер + БД + Telegram)  
**Стек:** Python 3.12, UV, FastAPI, PostgreSQL (удалённая), SQLAlchemy, Playwright, APScheduler, python-telegram-bot

---

## Эпики

| # | Эпик | Задачи | Статус |
|---|---|---|---|
| E1 | [Инфраструктура](epics/epic-1-infrastructure.md) | 4 | 🔲 Не начат |
| E2 | [База данных](epics/epic-2-database.md) | 3 | 🔲 Не начат |
| E3 | [Парсер Krisha.kz](epics/epic-3-parser.md) | 4 | 🔲 Не начат |
| E4 | [Планировщик](epics/epic-4-scheduler.md) | 2 | 🔲 Не начат |
| E5 | [Telegram Bot](epics/epic-5-telegram.md) | 4 | 🔲 Не начат |

**Итого: 17 задач**

---

## Версия 2

См. [plan-v2.md](plan-v2.md) — эпики E6–E8 (аналитика, скоринг, Telegram V2).

---

## Порядок выполнения

```
E1 (Инфраструктура)
  └─> E2 (БД)
        └─> E3 (Парсер)
              └─> E4 (Планировщик)
                    └─> E5 (Telegram)
```

---

## Структура проекта (целевая)

```
krisha_monitoring/
├── app/
│   ├── main.py
│   ├── config.py
│   ├── database.py
│   ├── models/
│   │   ├── apartment.py
│   │   ├── price_history.py
│   │   ├── seller.py
│   │   ├── residential_complex.py
│   │   └── notification.py
│   ├── repositories/
│   │   ├── apartment_repo.py
│   │   └── complex_repo.py
│   ├── scraper/
│   │   ├── krisha_scraper.py
│   │   └── parser.py
│   ├── scheduler/
│   │   └── jobs.py
│   ├── analyzer/
│   │   └── deal_analyzer.py
│   └── telegram/
│       ├── bot.py
│       └── handlers.py
├── alembic/
│   └── versions/
├── pyproject.toml
├── uv.lock
├── .env.example
└── docs/
```

---

## Локальный запуск

```bash
uv sync
uv run playwright install chromium
cp .env.example .env   # указать DATABASE_URL удалённой БД
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

**БД:** PostgreSQL уже развёрнута удалённо — подключение только через `DATABASE_URL` в `.env`. Локальный Postgres в Docker не используется.
```
