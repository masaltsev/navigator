# Варианты развёртывания на тестовый сервер (Ubuntu)

**Дата:** 2026-02-26  
**Область:** инфраструктура, backend (Laravel), ai-pipeline/harvester (Python), Redis, PostgreSQL  
**Источники:** `docs/Navigator_Core_Model_and_API.md`, `docs/README.md`, `ai-pipeline/harvester/README.md`, `backend/composer.json`, `ai-pipeline/harvester/pyproject.toml`, `ai-pipeline/harvester/docker-compose.yml`

---

## 1. Кратко о структуре репозитория и зависимостях

### 1.1 Два основных блока

| Блок | Путь | Стек | Зависимости |
|------|------|------|-------------|
| **Backend (Navigator Core)** | `backend/` | Laravel 12, PHP 8.2+ | PostgreSQL (с PostGIS для `venues.coordinates`), Redis (опционально для queue/cache), Node/npm (Vite) |
| **Harvester (AI pipeline)** | `ai-pipeline/harvester/` | Python 3.12, FastAPI, Celery | Redis (очереди), Crawl4AI + Playwright Chromium, DeepSeek API, опционально Dadata, Yandex Search |

### 1.2 Общие сервисы

- **PostgreSQL** — основная БД Laravel; для гео (venues) нужен **PostGIS**.
- **Redis** — очереди Celery (harvester), опционально queue/cache Laravel.
- Локально: Laravel под **Herd** (macOS), БД по умолчанию sqlite; на сервере — PostgreSQL.

### 1.3 Связка backend ↔ harvester

- Harvester дергает Core API: `CORE_API_URL` (например `https://backend.test` или URL тестового сервера), `CORE_API_TOKEN`.
- Laravel отдаёт сидеры в JSON: `php artisan seeders:export-json` → `ai-pipeline/harvester/seeders_data/`.
- При необходимости Laravel может триггерить harvest (по документации — `POST /harvest/run` или диспатч из Scheduler).

---

## 2. Что нужно на тестовом сервере (Ubuntu)

- **PHP** 8.2+ (рекомендуется 8.4), расширения: pdo_pgsql, redis, mbstring, xml, curl, zip, bcmath и др. (стандартный набор Laravel).
- **PostgreSQL** 15+ с **PostGIS** (миграция `create_venues_table` добавляет `geometry(Point, 4326)`).
- **Redis** (порт 6379).
- **Node.js** 18+ и npm (для `npm run build` в backend).
- **Python** 3.12, venv, pip; **Playwright** + Chromium (для harvester).
- Секреты: `APP_KEY`, `DB_*`, `CORE_API_*`, `DEEPSEEK_API_KEY`, при необходимости Dadata, Yandex Search.

---

## 3. Варианты быстрого развёртывания на Ubuntu

### Вариант A: Всё вручную (максимальный контроль)

1. Установить на сервер: PHP 8.2/8.4, PostgreSQL + PostGIS, Redis, Node, Python 3.12.
2. Клонировать репо, в `backend/`: `composer install --no-dev`, скопировать `.env` из `.env.example`, настроить `DB_CONNECTION=pgsql`, `DB_*`, `REDIS_*`, сгенерировать `APP_KEY`, запустить миграции, `npm ci && npm run build`.
3. В `ai-pipeline/harvester/`: создать venv, `pip install -e ".[dev]"`, `playwright install --with-deps chromium`, скопировать `.env`, настроить `CORE_API_URL` на URL бэкенда, `REDIS_URL`, ключи.
4. Запустить Laravel (php-fpm + nginx или `php artisan serve` для теста), Redis, Celery worker (`celery -A workers.celery_app worker …`).
5. Синхронизировать сидеры: из `backend/` выполнить `php artisan seeders:export-json` (или копировать уже сгенерированные `seeders_data/` с локальной машины).

**Плюсы:** нет зависимости от Docker, привычный стек. **Минусы:** дольше первичная настройка, нужно следить за версиями PHP/PostgreSQL/Python.

---

### Вариант B: Laravel Sail (один docker-compose для backend + БД + Redis)

- В `backend/` включить Sail (`sail: true` в boost или использовать Sail напрямую), добавить в `docker-compose.yml` сервисы: app (Laravel), pgsql (PostgreSQL + PostGIS), redis.
- На сервере: только Docker и Docker Compose. Запуск: `./vendor/bin/sail up -d`, миграции и сидеры через `sail artisan ...`.
- Harvester при этом можно либо запускать на хосте (Python + venv + Redis с хоста или из той же сети к Redis в Sail), либо позже добавить в общий compose.

**Плюсы:** быстрый старт backend + БД + Redis одной командой, окружение близко к продакшену. **Минусы:** на сервере нужен Docker; PostGIS нужно добавить в образ pgsql (официальный образ `postgis/postgis` или кастомный Dockerfile).

---

### Вариант C: Всё в Docker (общий docker-compose в корне репо)

- Создать в корне репозитория `docker-compose.yml`, объединяющий:
  - **postgres** + PostGIS (порт 5432, volume для данных);
  - **redis** (порт 6379);
  - **backend** (образ на базе `php:8.4-cli` или nginx+php-fpm, зависимости через composer, entrypoint — php-fpm или `artisan serve`);
  - **harvester-worker** (текущий Dockerfile из `ai-pipeline/harvester/`, образ уже есть);
  - при необходимости **harvester API** (uvicorn) для приёма запросов от Laravel.
- Backend в контейнере подключается к `postgres` и `redis` по именам сервисов; harvester — к `redis` и по `CORE_API_URL` к сервису backend.
- Сидеры: либо volume с хоста с заранее собранными `seeders_data/`, либо одноразовый job/скрипт после старта: запуск контейнера backend с `artisan seeders:export-json` и копирование результата в volume harvester.

**Плюсы:** единая команда `docker compose up -d`, воспроизводимое окружение. **Минусы:** нужно подготовить Dockerfile для Laravel (или использовать готовый образ типа `laravel/sail`-подобный с PHP + Node для build), настроить сети и переменные.

---

### Вариант D: Гибрид — только инфраструктура в Docker (PostgreSQL + Redis), приложения на хосте

- В корне или в `backend/` один `docker-compose.yml`: сервисы **postgres** (с PostGIS) и **redis**.
- На хосте: PHP (Laravel), Python (harvester), Node (build фронта). Приложения подключаются к `localhost:5432` и `localhost:6379`.
- Быстро поднять БД и Redis одной командой; версии PHP/Python контролируете сами (в т.ч. через herd-аналоги или системные пакеты).

**Плюсы:** быстрый старт инфраструктуры, привычная отладка приложений на хосте. **Минусы:** на сервере всё равно ставите PHP, Python, Node.

---

## 4. Рекомендация для «быстрого» тестового стенда

- **Самый быстрый путь:** **Вариант D** (Docker только для PostgreSQL + Redis) + ручная установка Laravel и Harvester на хосте. Либо **Вариант B** (Sail) только для backend + БД + Redis, Harvester на хосте с указанием `REDIS_URL` на Redis из Sail (проброс порта 6379).
- Для **полной изоляции и CI-подобия** позже можно перейти к **Варианту C** (общий compose с backend в контейнере).

---

## 5. Что сделать сейчас на локальной машине (Apple Silicon, Herd)

1. **Проверить, что сидеры экспортируются и подхватываются harvester’ом**  
   В `backend/`: `php artisan seeders:export-json`. Убедиться, что в `ai-pipeline/harvester/seeders_data/` появились актуальные JSON. Это понадобится и на сервере (или копировать эту папку).

2. **Собрать один раз образ harvester (опционально)**  
   Из `ai-pipeline/harvester/`: `docker compose build harvester-worker`. Так проверите, что Dockerfile и зависимости собираются без ошибок (в т.ч. на ARM; на Ubuntu будет amd64).

3. **Подготовить пример `.env` для тестового сервера**  
   - **Backend:** скопировать `backend/.env.example` в черновик `backend/.env.staging.example`, заменить `DB_CONNECTION=pgsql`, прописать плейсхолдеры для `DB_HOST`, `DB_DATABASE`, `DB_USERNAME`, `DB_PASSWORD`, `REDIS_*`, `APP_URL` (URL тестового сервера). Не коммитить реальные секреты.  
   - **Harvester:** в `ai-pipeline/harvester/.env.example` уже есть плейсхолдеры; добавить в README или в этот документ напоминание: на сервере выставить `CORE_API_URL` на URL тестового бэкенда и `REDIS_URL` на Redis сервера.

4. **Документировать минимальный набор переменных для теста**  
   В README или в `docs/` перечислить обязательные переменные для staging (APP_KEY, DB_*, CORE_API_URL, CORE_API_TOKEN, DEEPSEEK_API_KEY, REDIS_URL), чтобы на сервере не забыть ни одну.

5. **PostgreSQL + PostGIS на сервере**  
   Локально можно продолжать с sqlite; на Ubuntu для теста нужен именно PostgreSQL с PostGIS (миграция venues это требует). Имеет смысл один раз проверить миграции на локальной PostgreSQL с PostGIS (например через Docker), чтобы на сервере не было сюрпризов.

6. **Список портов для фаервола/безопасности**  
   Для тестового сервера: 80/443 (веб), 22 (SSH). Redis и PostgreSQL не открывать наружу или ограничить доступ (bind только localhost / приватная сеть).

---

## 6. Чек-лист перед первым деплоем на тестовый сервер

- [ ] На сервере установлены: PHP 8.2+, PostgreSQL с PostGIS, Redis, Node, Python 3.12.
- [ ] Создана БД и пользователь PostgreSQL; в `.env` backend заданы `DB_CONNECTION=pgsql` и корректные `DB_*`.
- [ ] Выполнены миграции: `php artisan migrate`.
- [ ] Сидеры экспортированы в `seeders_data/` и доступны harvester’у (или скопированы на сервер).
- [ ] В backend настроены `APP_KEY`, `APP_URL` (URL тестового сервера).
- [ ] В harvester настроены `CORE_API_URL`, `CORE_API_TOKEN`, `REDIS_URL`, `DEEPSEEK_API_KEY`.
- [ ] Redis запущен; Celery worker harvester’а подключается к тому же Redis.
- [ ] При необходимости: queue/cache Laravel переведены на Redis (`QUEUE_CONNECTION=redis`, `CACHE_STORE=redis`).

После этого можно повторить сценарий «один URL → harvester → Core API» уже на тестовом сервере.
