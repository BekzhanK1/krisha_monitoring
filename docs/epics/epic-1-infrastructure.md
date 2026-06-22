# Epic 1: Инфраструктура и настройка проекта

**Цель:** Подготовить рабочее окружение через UV, структуру папок, конфигурацию и локальный запуск.  
**Зависимости:** Нет  
**Следующий эпик:** [Epic 2 — База данных](epic-2-database.md)

> **БД:** PostgreSQL уже есть на удалённом сервере. Локальный Postgres / Docker для БД не нужен — только `DATABASE_URL` в `.env`.

---

## Задачи

| # | Задача | Статус |
|---|---|---|
| 1.1 | [Структура проекта и UV](#задача-11--структура-проекта-и-uv) | ✅ |
| 1.2 | [Локальный запуск через UV](#задача-12--локальный-запуск-через-uv) | ✅ |
| 1.3 | [Конфигурация через Pydantic Settings](#задача-13--конфигурация-через-pydantic-settings) | ✅ |
| 1.4 | [Логирование](#задача-14--логирование) | ✅ |

---

## Задача 1.1 — Структура проекта и UV

**Описание:** Инициализировать проект через UV, создать `pyproject.toml`, `uv.lock`, `.env.example`, `README.md`.

### Чеклист

- [x] `uv init` — инициализация проекта
- [x] `pyproject.toml` с зависимостями через `uv add`:
  - `fastapi`, `uvicorn[standard]`
  - `sqlalchemy[asyncio]`, `asyncpg`
  - `alembic`
  - `playwright`
  - `beautifulsoup4`, `lxml`
  - `apscheduler`
  - `python-telegram-bot`
  - `pydantic-settings`
  - `loguru`
  - `httpx`
- [x] Dev-зависимости через `uv add --dev`: `pytest`, `pytest-asyncio`, `mypy`, `ruff`
- [x] `uv.lock` закоммичен в репозиторий
- [x] Создать `.env.example` со всеми переменными
- [x] Создать `README.md` с командами `uv sync` / `uv run`

### Курсор-промпт

```
Ты разрабатываешь Python-проект "krisha_monitoring" — систему мониторинга недвижимости.

**Задача:** Создать базовую структуру проекта с UV.

**Менеджер зависимостей: UV** (не pip, не poetry).

**Создай следующие файлы и папки:**

1. Инициализировать проект: `uv init --python 3.12`

2. Добавить зависимости через uv add:
   fastapi, uvicorn[standard], sqlalchemy[asyncio], asyncpg, alembic,
   playwright, beautifulsoup4, lxml, apscheduler, python-telegram-bot>=21,
   pydantic-settings, loguru, httpx

   Dev: uv add --dev pytest pytest-asyncio mypy ruff

3. `.env.example`:
   DATABASE_URL=postgresql+asyncpg://user:password@host:5432/krisha_db
   TELEGRAM_BOT_TOKEN=
   TELEGRAM_CHAT_ID=
   PARSER_INTERVAL_MINUTES=30
   LOG_LEVEL=INFO

   DATABASE_URL — удалённая PostgreSQL, локальная БД не поднимается.

4. Пустые `__init__.py` в папках: app/, app/models/, app/repositories/,
   app/scraper/, app/scheduler/, app/analyzer/, app/telegram/

5. `app/main.py` — минимальное FastAPI приложение с lifespan, health-check GET /health

6. `README.md` — инструкция:
   uv sync
   uv run playwright install chromium
   cp .env.example .env
   uv run uvicorn app.main:app --reload

**Требования:**
- pyproject.toml + uv.lock (lockfile обязателен)
- Python 3.12+
- Без Docker Compose и без локального Postgres
```

---

## Задача 1.2 — Локальный запуск через UV

**Описание:** Настроить dev-окружение и проверить, что приложение стартует с удалённой БД.

### Чеклист

- [x] `.env` создан из `.env.example`, `DATABASE_URL` указывает на удалённую БД
- [x] `uv sync` — зависимости установлены
- [x] `uv run playwright install chromium` — браузер для парсера
- [x] `uv run uvicorn app.main:app --reload` — приложение стартует
- [x] `GET /health` возвращает 200
- [x] В README задокументированы все команды запуска

### Курсор-промпт

```
Ты разрабатываешь Python-проект "krisha_monitoring".

**Задача:** Настроить локальный dev-запуск через UV.

**НЕ создавать:**
- docker-compose.yml с Postgres
- локальный контейнер БД
- pip install / requirements.txt

**Сделать:**

1. Обновить README.md — раздел "Локальный запуск":
   ```bash
   uv sync
   uv run playwright install chromium
   cp .env.example .env   # заполнить DATABASE_URL удалённой БД
   uv run uvicorn app.main:app --reload
   ```

2. Добавить в README раздел "Миграции":
   ```bash
   uv run alembic upgrade head
   ```

3. Добавить в README раздел "Тесты":
   ```bash
   uv run pytest
   uv run ruff check .
   ```

4. Убедиться, что GET /health работает без локальной БД в docker
   (подключение к удалённой PostgreSQL через DATABASE_URL из .env)

**Требования:**
- Все команды только через `uv run`
- DATABASE_URL — единственный способ подключения к БД
```

---

## Задача 1.3 — Конфигурация через Pydantic Settings

**Описание:** Централизованная конфигурация через `app/config.py`.

### Чеклист

- [x] Класс `Settings(BaseSettings)` с валидацией всех переменных
- [x] Читает из `.env` файла
- [x] Singleton через `@lru_cache`
- [x] `database_url` — URL удалённой PostgreSQL
- [x] Все компоненты импортируют конфиг только из `app/config.py`

### Курсор-промпт

```
Ты разрабатываешь Python-проект "krisha_monitoring".

**Задача:** Создать `app/config.py` с централизованной конфигурацией.

**Требования:**

1. Использовать `pydantic-settings` v2, класс `Settings(BaseSettings)`
2. Поля:
   - database_url: str  # удалённая PostgreSQL, формат postgresql+asyncpg://...
   - telegram_bot_token: str
   - telegram_chat_id: int
   - parser_interval_minutes: int = 30
   - log_level: str = "INFO"
   - environment: Literal["development", "production"] = "development"
3. `model_config = SettingsConfigDict(env_file=".env", extra="ignore")`
4. Функция `get_settings()` с декоратором `@lru_cache()` — возвращает синглтон

**Файл:** `app/config.py`
```

---

## Задача 1.4 — Логирование

**Описание:** Настроить `loguru` с форматом, ротацией и уровнями из конфига.

### Чеклист

- [x] `app/logging_config.py` — настройка loguru
- [x] Формат: `{time:YYYY-MM-DD HH:mm:ss} | {level} | {name}:{line} | {message}`
- [x] Ротация файла `logs/app.log` каждые 10 MB, retention 7 дней
- [x] В `app/main.py` вызов `setup_logging()` при старте
- [x] `logs/` добавлен в `.gitignore`

### Курсор-промпт

```
Ты разрабатываешь Python-проект "krisha_monitoring".

**Задача:** Настроить логирование через loguru.

**Создай `app/logging_config.py`:**

```python
from loguru import logger
from app.config import get_settings

def setup_logging() -> None:
    settings = get_settings()
    logger.remove()
    # stdout handler
    # file handler с ротацией
```

**Требования:**
- Уровень логирования из `settings.log_level`
- stdout: цветной вывод, формат с временем, модулем и строкой
- Файл logs/app.log: ротация 10 MB, retention="7 days", compression="zip"
- В app/main.py импортировать и вызвать setup_logging() в lifespan до старта
- Добавить logs/ в .gitignore (если ещё не добавлен)
```
