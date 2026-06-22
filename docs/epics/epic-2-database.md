# Epic 2: База данных

**Цель:** Описать схему PostgreSQL через SQLAlchemy, настроить Alembic-миграции и создать репозитории для работы с данными.  
**Зависимости:** [Epic 1](epic-1-infrastructure.md)  
**Следующий эпик:** [Epic 3 — Парсер](epic-3-parser.md)

> **БД:** Миграции и все запросы идут на удалённую PostgreSQL через `DATABASE_URL` из `.env`. Локальный Postgres не поднимается.

---

## Задачи

| # | Задача | Статус |
|---|---|---|
| 2.1 | [Модели SQLAlchemy](#задача-21--модели-sqlalchemy) | ✅ |
| 2.2 | [Alembic миграции](#задача-22--alembic-миграции) | ✅ |
| 2.3 | [Репозитории (DAL)](#задача-23--репозитории-dal) | ✅ |

---

## Задача 2.1 — Модели SQLAlchemy

**Описание:** Создать все ORM-модели для таблиц из ТЗ.

### Чеклист

- [x] `app/database.py` — async engine, sessionmaker, Base
- [x] `app/models/residential_complex.py` — таблица `residential_complexes`
- [x] `app/models/apartment.py` — таблица `apartments` (все 21 поле из ТЗ)
- [x] `app/models/price_history.py` — таблица `apartment_prices`
- [x] `app/models/status_history.py` — таблица `apartment_status_history`
- [x] `app/models/seller.py` — таблица `sellers`
- [x] `app/models/notification.py` — таблица `notifications`
- [x] Все модели импортированы в `app/models/__init__.py`

### Схема таблиц

```sql
residential_complexes:
  id, name, district, city, created_at

apartments:
  id, external_id (уникальный), url, complex_id (FK),
  price, price_per_sqm, district, address, rooms,
  total_area, living_area, kitchen_area, floor, total_floors,
  year_built, house_type, ceiling_height, condition, balcony,
  bathroom, description, photos (JSONB), seller_type,
  is_active, first_seen_at, last_seen_at, updated_at

apartment_prices:
  id, apartment_id (FK), price, price_per_sqm, recorded_at

apartment_status_history:
  id, apartment_id (FK), status (active/inactive/price_changed),
  old_price, new_price, changed_at

sellers:
  id, apartment_id (FK), name, phone, seller_type (owner/agent/agency),
  owner_probability (Float), created_at

notifications:
  id, apartment_id (FK), notification_type, message, sent_at, is_sent
```

### Курсор-промпт

```
Ты разрабатываешь Python-проект "krisha_monitoring".

**Задача:** Создать ORM-модели SQLAlchemy (async).

**Создай `app/database.py`:**
- Async engine через `create_async_engine(settings.database_url)`
- `AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)`
- `Base = DeclarativeBase()`
- Dependency `get_db()` — async generator для FastAPI

**Создай модели в `app/models/`:**

Используй следующие соглашения:
- `mapped_column()` и `Mapped[type]` (SQLAlchemy 2.0 стиль)
- `DateTime(timezone=True)` для всех временных полей
- `server_default=func.now()` для `created_at`
- `onupdate=func.now()` для `updated_at`
- `ForeignKey` с `ondelete="CASCADE"` где уместно

Модели (по схеме выше):
1. ResidentialComplex → app/models/residential_complex.py
2. Apartment → app/models/apartment.py (photos: JSONB тип через sa.JSON)
3. ApartmentPrice → app/models/price_history.py
4. ApartmentStatusHistory → app/models/status_history.py
5. Seller → app/models/seller.py (owner_probability: Float)
6. Notification → app/models/notification.py

В `app/models/__init__.py` — реэкспортировать все модели.

**Требования:**
- Только SQLAlchemy 2.0 синтаксис (никакого Column() старого стиля)
- Все FK — typed relationships
- Индексы на: apartment.external_id, apartment.complex_id, apartment.is_active
```

---

## Задача 2.2 — Alembic миграции

**Описание:** Инициализировать Alembic и создать начальную миграцию.

### Чеклист

- [x] Alembic инициализирован (`uv run alembic init alembic`)
- [x] `alembic/env.py` настроен для async и автоимпорта моделей
- [x] `alembic.ini` — `sqlalchemy.url` читается из `DATABASE_URL` в `.env`
- [x] Создана первая миграция `32839c6e60c9_initial_schema.py`
- [x] Миграция применена на удалённой БД: `uv run alembic upgrade head`
- [x] `uv run alembic downgrade -1` откатывает корректно

### Курсор-промпт

```
Ты разрабатываешь Python-проект "krisha_monitoring".

**Задача:** Настроить Alembic для async SQLAlchemy.

**БД:** удалённая PostgreSQL, URL из DATABASE_URL в .env. Локальный Postgres не используется.

**Шаги:**

1. В `alembic/env.py` внести изменения:
   - Импортировать `Base` из `app.models`
   - Импортировать все модели (чтобы Alembic их видел)
   - Настроить `target_metadata = Base.metadata`
   - Использовать async-режим: `run_async_migrations()` через `asyncio.run()`
   - `config.set_main_option("sqlalchemy.url", settings.database_url)`

2. В `alembic.ini`:
   - Убрать захардкоженный `sqlalchemy.url`

3. Создать миграцию:
   ```
   uv run alembic revision --autogenerate -m "initial_schema"
   uv run alembic upgrade head
   ```

**Требования:**
- Все команды через `uv run`
- Миграции применяются на удалённую БД из .env
- Поддержка `--autogenerate` для будущих изменений схемы
```

---

## Задача 2.3 — Репозитории (DAL)

**Описание:** Создать слой доступа к данным для apartment и residential_complex.

### Чеклист

- [x] `app/repositories/apartment_repo.py`:
  - `upsert_apartment()` — вставить или обновить по `external_id`
  - `get_active_by_complex()` — все активные квартиры ЖК
  - `mark_inactive()` — пометить объявление неактивным
  - `get_by_external_id()` — найти по ID с krisha.kz
- [x] `app/repositories/complex_repo.py`:
  - `get_or_create()` — найти ЖК по имени или создать
  - `get_all()` — список всех ЖК
- [x] `app/repositories/price_repo.py`:
  - `record_price_change()` — сохранить изменение цены
  - `get_price_history()` — история цен квартиры

### Курсор-промпт

```
Ты разрабатываешь Python-проект "krisha_monitoring".

**Задача:** Создать репозитории (Data Access Layer) для работы с БД.

**Создай `app/repositories/apartment_repo.py`:**

Функции (все async, принимают `session: AsyncSession`):

1. `upsert_apartment(session, data: dict) -> Apartment`
   - Проверить наличие по external_id
   - Если существует — обновить поля price, price_per_sqm, last_seen_at
   - Если новое — вставить
   - Если цена изменилась — записать в ApartmentPrice и ApartmentStatusHistory
   - Вернуть (apartment, is_new: bool, price_changed: bool)

2. `get_active_by_complex(session, complex_id: int) -> list[Apartment]`

3. `mark_inactive(session, external_ids_to_keep: list[str], complex_id: int) -> int`
   - Все квартиры ЖК, которых нет в списке — пометить is_active=False
   - Записать в status_history
   - Вернуть количество помеченных

4. `get_by_external_id(session, external_id: str) -> Apartment | None`

**Создай `app/repositories/complex_repo.py`:**

1. `get_or_create(session, name: str, district: str = "") -> ResidentialComplex`
2. `get_all(session) -> list[ResidentialComplex]`

**Требования:**
- Все операции через переданную `session` (не создавать сессию внутри)
- Использовать `select()`, `insert()` из sqlalchemy.orm
- Типизация: все функции с аннотациями типов
```
