# Развёртывание БД: прод, стейдж, свежий клон

Два сценария деплоя базы и почему на проде могла оказаться старая схема.

**Источник истины:** `database/schema/pgsql-schema.sql` (после `schema:dump --prune`), [BRANCH_AND_RELEASE_STRATEGY.md](./BRANCH_AND_RELEASE_STRATEGY.md).

---

## Два сценария

### 1. Восстановление из полного дампа (прод / копия прод)

Используется, когда есть готовый дамп с данными.

**Рекомендуется SQL-формат** — совместим с разными версиями PostgreSQL (например, дамп с pg 16 без проблем восстанавливается на pg 15). Файл: `backend/database/dumps/navigator_prod_YYYYMMDD.sql`.

1. На сервере: создать пустую БД (или пересоздать).
2. Восстановить дамп.

   **SQL (plain):**
   ```bash
   psql -h localhost -U navigator_core_user -d navigator_core -f /path/to/navigator_prod_YYYYMMDD.sql
   ```

   Бинарный формат (если версии pg на машине дампа и на сервере совпадают):
   ```bash
   pg_restore -d navigator_core --no-owner --no-privileges /path/to/navigator_prod_dump_*.dump
   ```

3. **Не выполнять** `php artisan migrate` и **не выполнять** `php artisan db:seed` — схема и справочные данные уже в дампе.

Если после такого восстановления запустить `db:seed`, сидеры могут ожидать колонки/таблицы из актуальной схемы; при этом в дампе уже есть засеянные данные — возможны дубли или ошибки. Прод после восстановления из дампа — только приложение (config:cache, queue:restart и т.д.).

### 2. Свежая БД из репозитория (стейдж, новый сервер, CI)

Клонируем репозиторий с `main` (или нужной веткой). В репо:

- `database/schema/pgsql-schema.sql` — полная актуальная схема (включая `description`, `keywords` в `thematic_categories` и т.д.);
- `database/migrations/` — только `.gitkeep`, без старых PHP-миграций (они «схлопнуты» в schema dump).

На сервере:

1. Создать пустую БД.
2. Выполнить:
   ```bash
   cd backend
   php artisan migrate --force
   ```
3. При первом запуске на **пустой** БД Laravel сначала загружает `database/schema/pgsql-schema.sql`, затем выполняет миграции из `database/migrations/` (их нет — только актуальная схема из дампа).
4. Засеять справочники при необходимости:
   ```bash
   php artisan db:seed --force
   ```

В этом сценарии схема берётся из файла, а не из старых миграций — стейдж и любой свежий клон получают корректную схему и сидеры работают.

---

## Почему на проде оказалась старая схема

Миграции на проде «успешно прошли», но таблицы без `description`/`keywords`, потому что:

- либо на сервере был **старый клон** репозитория (до `schema:dump --prune`), в котором в `database/migrations/` лежали **только старые** PHP-миграции (без `extend_ontology_fields` и т.п.);
- либо деплой делался в момент, когда в репо ещё не было актуального `pgsql-schema.sql` и «схлопнутых» миграций.

В такой ситуации Laravel при пустой БД не находит schema dump (или не использует его) и гоняет только PHP-файлы из `migrations/`. Если среди них нет миграции, добавляющей `description`/`keywords`, схема остаётся старой, и `db:seed` падает с «column does not exist».

**Итог:** после перехода на схему через `schema:dump --prune` и выкладки этого состояния в `main`:

- **Свежий клон** (стейдж, новый сервер): `migrate` загружает `pgsql-schema.sql` → схема актуальная → сидеры работают.
- **Прод:** лучше поднимать БД из полного дампа и не запускать migrate/seed после восстановления.

---

## Краткий чек-лист

| Окружение | Действия с БД |
|-----------|----------------|
| Прод (есть дамп) | Создать/пересоздать БД → восстановить из `.sql` (`psql ... -f`) или из `.dump` (`pg_restore`) → **не** migrate, **не** seed |
| Стейдж / новый сервер | Пустая БД → `php artisan migrate --force` → при необходимости `php artisan db:seed --force` |

При деплое из `main` после мержа релиза в репозитории всегда актуальны `database/schema/pgsql-schema.sql` и пустой (кроме `.gitkeep`) каталог миграций — клонирование и `migrate` на пустой БД будут давать правильную схему.

---

## Создание дампа для прод/стейджа

**SQL (рекомендуется при разных версиях pg на сервере):**

```bash
cd backend
PGPASSWORD=... pg_dump -h 127.0.0.1 -p 5432 -U navigator_core_user -d navigator_core \
  --no-owner --no-privileges -F p \
  -f database/dumps/navigator_prod_$(date +%Y%m%d).sql
```

`-F p` — plain SQL, без проблем восстанавливается через `psql` на pg 15, 16 и т.д.

**Бинарный (custom):** заменить `-F p` на `-F c` и расширение файла на `.dump`; восстанавливать через `pg_restore`. Версия `pg_restore` на сервере должна быть не старше версии `pg_dump`, с которой делали дамп.

**Swagger / OpenAPI:** спека лежит в репозитории в `backend/docs/openapi.yaml` и отдаётся по `GET /api/documentation/spec`. Страница документации: `/api/documentation`. Если на проде был 404 на `/api/documentation/spec` — убедиться, что в деплое есть файл `docs/openapi.yaml` (он коммитится в репо).
