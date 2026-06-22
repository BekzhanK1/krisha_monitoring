# Krisha Monitoring

AI-платформа мониторинга недвижимости Krisha.kz для поиска инвестиционно привлекательных квартир.

**Стек:** Python 3.12, UV, FastAPI, PostgreSQL (удалённая), Playwright, APScheduler, python-telegram-bot

---

## Локальный запуск

```bash
uv sync
uv run playwright install chromium
cp .env.example .env   # заполнить DATABASE_URL удалённой БД
uv run uvicorn app.main:app --reload
```

Приложение доступно на http://127.0.0.1:8000

Проверка health-check:

```bash
curl http://127.0.0.1:8000/health
# {"status":"ok"}
```

> **БД:** PostgreSQL развёрнута удалённо. Локальный Postgres / Docker для БД не используется — только `DATABASE_URL` в `.env`.

---

## Миграции

```bash
uv run alembic upgrade head
```

Создать новую миграцию после изменения моделей:

```bash
uv run alembic revision --autogenerate -m "описание"
```

---

## Тесты

```bash
uv run pytest
uv run ruff check .
uv run mypy app
```

---

## Переменные окружения

| Переменная | Описание |
|---|---|
| `DATABASE_URL` | URL удалённой PostgreSQL (`postgresql+asyncpg://...`) |
| `TELEGRAM_BOT_TOKEN` | Токен Telegram-бота |
| `TELEGRAM_CHAT_ID` | ID чата для уведомлений |
| `PARSER_INTERVAL_MINUTES` | Интервал парсинга (по умолчанию 30) |
| `LOG_LEVEL` | Уровень логирования (по умолчанию INFO) |
