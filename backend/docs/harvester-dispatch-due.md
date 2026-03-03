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

В `routes/console.php` уже добавлен закомментированный пример:

```php
// Schedule::command('harvest:dispatch-due', ['--limit' => 100])->daily()->at('02:00');
```

Раскомментируйте и при необходимости измените время или частоту. На сервере должен быть запущен планировщик Laravel:

- в режиме разработки: `php artisan schedule:work`;
- в production: в crontab одна строка: `* * * * * cd /path/to/backend && php artisan schedule:run >> /dev/null 2>&1`.

## Критерий due

Источник считается «пора обходить», если:

- `is_active = true`;
- `deleted_at IS NULL`;
- `organizer_id` задан;
- `last_crawled_at` пусто **или** `last_crawled_at + crawl_period_days` уже в прошлом.

Выборка совпадает с эндпоинтом `GET /api/internal/sources/due` (модель `Source::scopeDue()`).
