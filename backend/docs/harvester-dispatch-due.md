# Плановый обход источников: отправка due sources в Harvester

**Дата:** 2026-02-25  
**Источник истины:** [docs/Navigator_Core_Model_and_API.md](../../docs/Navigator_Core_Model_and_API.md) (раздел 4.0, 4.5).

## Назначение

Команда `harvest:dispatch-due` выбирает источники, которые пора обойти (due), и отправляет их в Harvester одним запросом `POST /harvest/run`. Harvester ставит задачи в Celery и обходит сайты; после обхода обновляет `last_crawled_at` и `last_status` в Core через PATCH /sources/{id}.

## Конфигурация

В `.env` бэкенда:

```env
HARVESTER_URL=http://localhost:8100
HARVESTER_API_TOKEN=your-shared-token
```

`HARVESTER_API_TOKEN` должен совпадать с тем, что настроен в Harvester (переменная `HARVESTER_API_TOKEN` в `.env` пайплайна), иначе Harvester вернёт 401.

**Локально:** если эти переменные не заданы, `harvest:dispatch-due` без `--dry-run` завершится с ошибкой («must be set in .env»). Цепочка backend → Harvester по due sources работает только при заданных `HARVESTER_URL` и `HARVESTER_API_TOKEN` и при запущенном Harvester API (и при необходимости Redis/Celery). Для проверки списка due без вызова Harvester используйте `php artisan harvest:dispatch-due --dry-run`.

## Использование

```bash
# Сухой прогон: только показать, какие источники ушли бы
php artisan harvest:dispatch-due --dry-run

# Отправить до 100 due sources (по умолчанию)
php artisan harvest:dispatch-due

# Отправить до 200
php artisan harvest:dispatch-due --limit=200
```

Максимум `--limit` — 500 (ограничение API due).

## Расписание

В `routes/console.php` включено ежедневное выполнение в 02:00:

```php
Schedule::command('harvest:dispatch-due', ['--limit' => 100])->daily()->at('02:00');
```

Чтобы команда реально запускалась по расписанию, на сервере должен быть запущен планировщик Laravel:

- в режиме разработки: `php artisan schedule:work`;
- в production: в crontab одна строка: `* * * * * cd /path/to/backend && php artisan schedule:run >> /dev/null 2>&1`.

## Критерий due

Источник считается «пора обходить», если:

- `is_active = true`;
- `deleted_at IS NULL`;
- `organizer_id` задан;
- `last_crawled_at` пусто **или** `last_crawled_at + crawl_period_days` уже в прошлом.

Выборка совпадает с эндпоинтом `GET /api/internal/sources/due` (модель `Source::scopeDue()`).

---

## Чеклист для продакшена: автоматика по due sources

Чтобы по расписанию зажигались обходы источников (due → POST /harvest/run → Celery), на проде должны быть подняты и настроены все звенья цепочки.

### Цепочка

1. **Cron** раз в минуту вызывает `php artisan schedule:run`.
2. **Laravel Scheduler** раз в сутки (02:00) запускает `harvest:dispatch-due --limit=100`.
3. **DispatchHarvestDueCommand** запрашивает у Core due sources и шлёт `POST /harvest/run` в Harvester API (тело: список источников).
4. **Harvester API** (uvicorn) принимает запрос и ставит в очередь Celery по одной задаче `crawl_and_enrich` на каждый источник.
5. **Redis** — брокер и backend для Celery.
6. **Celery worker** забирает задачи из Redis, выполняет краул и по завершении вызывает Core API `PATCH /sources/{id}` (last_status, last_crawled_at).

### Что должно быть запущено на проде

| Компонент | Где / как запустить |
|-----------|----------------------|
| **Redis** | Сервис на порту 6379 (например `docker compose up -d redis` в `ai-pipeline/harvester/` или системный redis). |
| **Harvester API** | `uvicorn api.harvest_api:app --host 0.0.0.0 --port 8100` из `ai-pipeline/harvester/` (systemd, Docker или другой процесс-менеджер). В стандартном `docker-compose.yml` этого сервиса нет — только redis + harvester-worker (Celery); API нужно запускать отдельно или добавить сервис в compose. |
| **Celery worker** | `celery -A workers.celery_app worker --loglevel=info --concurrency=4` из `ai-pipeline/harvester/` (тот же Redis по `REDIS_URL`). |
| **Laravel cron** | В crontab: `* * * * * cd /path/to/backend && php artisan schedule:run >> /dev/null 2>&1`. |

### Бэкенд и пайплайн на одном сервере

Если и Laravel, и Harvester (API + worker) на одной машине:

- **HARVESTER_URL** — как бэкенд достучится до uvicorn:
  - API на хосте (systemd, screen) на порту 8100: `http://127.0.0.1:8100` или `http://localhost:8100`;
  - API в Docker с пробросом `8100:8100`: с хоста то же `http://127.0.0.1:8100`;
  - бэкенд и API в одной Docker-сети, API — отдельный сервис: `http://<имя-сервиса>:8100`.
- **HARVESTER_API_TOKEN** — один и тот же в `.env` бэкенда и в `.env` Harvester.

### Переменные окружения

**Backend (`.env`):**

- `HARVESTER_URL` — базовый URL Harvester API (на одном сервере с бэкендом обычно `http://127.0.0.1:8100`; в Docker-сети — `http://harvester-api:8100` и т.п.).
- `HARVESTER_API_TOKEN` — токен; должен совпадать с `HARVESTER_API_TOKEN` в Harvester.

**Harvester (`.env` в `ai-pipeline/harvester/`):**

- `REDIS_URL` — подключение к Redis (например `redis://localhost:6379/0` или `redis://redis:6379/0` в Docker).
- `HARVESTER_API_TOKEN` — тот же токен, что и в бэкенде.
- `CORE_API_URL`, `CORE_API_TOKEN` — чтобы воркер мог вызывать Core API (import_organizer, update_source).
- При необходимости: ключи DeepSeek, Dadata и т.д. для полного пайплайна.

### Проверка

- Сухой прогон с бэкенда: `php artisan harvest:dispatch-due --dry-run` — показывает, сколько источников ушло бы в Harvester.
- Ручной запуск: `php artisan harvest:dispatch-due --limit=5` — отправить 5 due sources; убедиться, что воркер их обрабатывает и в Core обновляются `last_crawled_at` / `last_status`.
- Harvester: `GET /health` и при необходимости `GET /harvest/status/{task_id}` после POST /harvest/run.
