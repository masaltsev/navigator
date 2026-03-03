# Отчёт: Source CRUD API + Auto-Enrich Pipeline — Sprint 5

- **Дата:** 2026-02-25
- **Commit:** 5110c01 (pre-commit; изменения ещё не закоммичены)
- **Область:** Core API (Laravel) + AI Pipeline (Harvester) — управление источниками через API, автоматическое обогащение организаций без источников, централизация конфигурации
- **Source of truth:** docs/Navigator_Core_Model_and_API.md

## Контекст

По результатам предыдущего спринта (обогащение 171 сломанной ссылки) вся работа с БД велась напрямую через `psycopg2` — потому что в Core API **не было эндпоинтов для управления источниками (Sources)**. Это было ad-hoc решение, не подходящее для долгосрочной автоматизации.

Для следующей задачи — обогащение ~2847 организаций без источников — принято решение **API-first**: сначала добавить универсальные эндпоинты в Core, затем строить автоматизацию поверх API.

---

## Что сделано

### Фаза 1: Core API — Source CRUD (Laravel)

**Новый файл:** `backend/app/Http/Controllers/Internal/SourceController.php`

Реализованы 3 эндпоинта под middleware `auth.internal` (Bearer Token):

| Метод | Путь | Назначение |
|-------|------|------------|
| `GET` | `/api/internal/sources` | Список источников по `organizer_id` (фильтры: `kind`, `is_active`) |
| `POST` | `/api/internal/sources` | Создание нового источника. Проверяет дубликат `(organizer_id, base_url)`. При `kind=org_website` обновляет `organizations.site_urls` |
| `PATCH` | `/api/internal/sources/{id}` | Обновление URL, статуса, активности. Синхронизирует `site_urls`. Возвращает 409 при конфликте |

**Дополнительный эндпоинт** в `ImportController`:

| Метод | Путь | Назначение |
|-------|------|------------|
| `GET` | `/api/internal/organizations/without-sources` | Пагинированный список организаций без активных источников. Возвращает `org_id`, `organizer_id`, `title`, `inn` |

**Роуты зарегистрированы** в `backend/routes/api.php`.

### Фаза 2: NavigatorCoreClient (Python)

**Файл:** `ai-pipeline/harvester/core_client/api.py`

Добавлены 4 метода (с retry, mock mode, метриками — тот же паттерн что у `import_organizer`):

- `create_source(organizer_id, base_url, kind, name)` — POST
- `update_source(source_id, base_url, last_status, is_active)` — PATCH
- `list_sources(organizer_id, kind)` — GET
- `get_orgs_without_sources(page, per_page)` — GET

Добавлены HTTP-хелперы `_patch()` и `_get()`.

### Фаза 3: auto_enrich.py — Background Runner

**Новый файл:** `ai-pipeline/harvester/scripts/auto_enrich.py`

Скрипт для длительного фонового прогона обогащения организаций без источников:

- **Вход:** загружает организации через `GET /organizations/without-sources` (пагинация)
- **Обработка:** каждая организация проходит через `EnrichmentPipeline.enrich_missing_source()`
- **AUTO (conf >= 0.8):** создаёт source `org_website` через `POST /sources` + социальные источники, если найдены
- **REJECT + соцсети:** если сайт не найден, но верифицированы страницы ВК/ОК — автоматически создаёт источники `vk_group`/`ok_group` через API
- **REVIEW (0.5-0.8):** сохраняет в `review.json` для ручной проверки
- **REJECT (< 0.5, без соцсетей):** сохраняет в `reject.json`
- **Crash recovery:** прогресс в JSONL (append-only), автоматический resume по `--run-id`
- **Graceful shutdown:** обрабатывает SIGINT/SIGTERM, завершает текущий item
- **Batch rate limiting:** `--batch-size`, `--batch-delay`, `--item-delay`
- **Периодическая статистика:** tier distribution, rate, ETA, DeepSeek cache hit, API calls

### Фаза 4: Централизация конфигурации (settings refactor)

**Файл:** `ai-pipeline/harvester/config/settings.py`

Полная централизация доступа к переменным окружения: `HarvesterSettings` (Pydantic) стал единым реестром **всех 22 env-переменных** с кэшированным синглтоном через `@lru_cache`. Ранее ~50 вызовов `os.getenv()` были разбросаны по 15+ файлам с дублированием дефолтов.

**Добавлены поля:**

| Группа | Новые поля |
|--------|-----------|
| Web Search | `search_provider`, `yandex_search_folder_id`, `yandex_search_api_key` |
| Harvester API | `harvester_api_token` |
| Logging | `harvester_log_format`, `harvester_log_level` |
| Database | `db_host`, `db_port`, `db_database`, `db_username`, `db_password` |

**Рефакторинг:** все `os.getenv()` заменены на `get_settings()` в 15 файлах:

- **Scripts:** `auto_enrich`, `enrich_sources`, `verify_social`, `patch_sources`, `run_single_url`, `batch_test`
- **Search:** `provider`, `yandex_xml_provider`, `site_verifier`
- **Workers:** `celery_app`, `tasks`
- **Strategies:** `multi_page`, `event_discovery`, `firecrawl_strategy`
- **Config:** `logging`, `llm_config`
- **API:** `harvest_api`
- **Aggregators:** `silverage_pipeline`, `sonko_pipeline`, `fpg_pipeline`
- **Tests:** `test_integration_deepseek`

**Результат:** `os.getenv()` в кодовой базе = 0. Все переменные окружения объявлены в одном месте с типизацией и дефолтами.

### Фаза 5: Wrapper с автоперезапуском

**Новый файл:** `ai-pipeline/harvester/scripts/run_auto_enrich.sh`

Bash-обёртка для `auto_enrich.py` с автоперезапуском:

- До 3 попыток при падении
- 30 секунд пауза между попытками
- Все логи дублируются в `data/runs/{run-id}/wrapper.log`
- При успешном завершении (exit 0) — останавливается
- После 3 неудач — финальное сообщение с инструкцией для ручного перезапуска

### Фаза 6: Документация

**Файл:** `docs/Navigator_Core_Model_and_API.md`

Раздел 4 "API для управления источниками" обновлён: добавлены спецификации всех 4 эндпоинтов (request/response, логика, query-параметры).

---

## Тестирование

### API endpoints (curl)

Все 4 эндпоинта протестированы вручную:

- `GET /organizations/without-sources?per_page=3` — 2847 total, пагинация работает
- `POST /sources` — source создан, `site_urls` обновлён
- `POST /sources` (дубликат) — `status: "exists"`, без ошибки
- `PATCH /sources/{id}` — URL обновлён, `site_urls` синхронизирован
- `GET /sources?organizer_id=...` — список источников организатора

### Smoke test (auto_enrich.py, 10 items)

```
Run ID: smoke_test_10
Items: 10
AUTO: 1 (КЦСОН → https://snkkcson.ru/, conf=0.95)
REVIEW: 0
REJECT: 9
ERROR: 0
Rate: 2.8 items/min
DeepSeek cost: $0.0017
```

Результат AUTO был создан как source в БД через API, `site_urls` обновлён автоматически. 9 REJECT — ожидаемо: это организации с очень общими названиями ("Светоч", "ВСМ", "ВЫШКА"), для которых DuckDuckGo не находит релевантных результатов.

---

## Архитектура: поток обогащения

```
auto_enrich.py (wrapper: run_auto_enrich.sh)
  │
  ├── GET /organizations/without-sources ──→ Core API (Laravel)
  │
  ├── Для каждой организации:
  │     │
  │     ├── EnrichmentPipeline.enrich_missing_source()
  │     │     ├── Web Search (Yandex API)
  │     │     ├── Pre-filter (агрегаторы, junk, нормализация)
  │     │     ├── Crawl + LLM verify (top-3 кандидата)
  │     │     └── Full Harvest (только AUTO: multi-page + OrgProcessor)
  │     │
  │     ├── AUTO (conf >= 0.8):
  │     │     ├── POST /sources (kind=org_website) ──→ Core API
  │     │     └── POST /sources (kind=vk_group/ok_group) ──→ Core API (если найдены)
  │     │
  │     ├── REJECT + verified social:
  │     │     └── POST /sources (kind=vk_group/ok_group) ──→ Core API
  │     │
  │     ├── REVIEW: → review.json
  │     └── REJECT (без соцсетей): → reject.json
  │
  └── progress.jsonl (crash recovery)
```

**Синхронизация `organizations.site_urls`:** происходит автоматически в Laravel `SourceController` при создании/обновлении source с `kind=org_website`. Для социальных источников (`vk_group`, `ok_group`) синхронизация не требуется.

---

## Структура файлов

```
ai-pipeline/harvester/
  config/settings.py              # единый реестр всех env-переменных (22 поля)
  scripts/auto_enrich.py          # background runner
  scripts/run_auto_enrich.sh      # wrapper с автоперезапуском (3 попытки)
  data/runs/{run_id}/
    progress.jsonl                # append-only аудит-лог (1 строка = 1 организация)
    review.json                   # REVIEW-результаты для ручной проверки
    reject.json                   # REJECT-результаты
    run_config.json               # сохранённые CLI-аргументы
    run_summary.json              # итоговая статистика (обновляется каждый batch)
    wrapper.log                   # лог wrapper-скрипта (при использовании)

backend/
  app/Http/Controllers/Internal/SourceController.php  # Source CRUD API
  routes/api.php                                      # роуты (4 новых)
```

## CLI

```bash
# Тестовый прогон (20 items)
python -m scripts.auto_enrich --run-id test_20 --max-items 20

# Полный прогон через wrapper (автоперезапуск)
bash scripts/run_auto_enrich.sh 2026-02-25_no_sources

# Полный прогон в фоне через wrapper
nohup bash scripts/run_auto_enrich.sh 2026-02-25_no_sources \
  > data/runs/2026-02-25_no_sources/wrapper.log 2>&1 &

# Resume после обрыва (тот же run-id)
python -m scripts.auto_enrich --run-id 2026-02-25_no_sources

# Мониторинг
cat data/runs/2026-02-25_no_sources/run_summary.json
wc -l data/runs/2026-02-25_no_sources/progress.jsonl
```

## Бэкап БД

```
data/backups/navigator_core_pre_auto_enrich_20260225_164817.dump
```

Восстановление:
```bash
pg_restore -h 127.0.0.1 -U navigator_core_user -d navigator_core --clean \
  data/backups/navigator_core_pre_auto_enrich_20260225_164817.dump
```

## Оценка стоимости полного прогона (2847 орг.)

- Yandex Search: ~2 847 запросов = ~1 367 RUB (~$15)
- DeepSeek verify (~2K tokens x 3 кандидата): ~$3
- DeepSeek harvest (~30K tokens, ожидается ~30-40% AUTO): ~$15-23
- Crawl4AI: бесплатно (self-hosted Playwright)
- **Итого: ~$33-41 + 1 367 RUB**

## Следующие шаги

1. ~~Подключить Yandex Search API в `.env`~~ — подключен (`SEARCH_PROVIDER=yandex`)
2. **Запустить полный прогон** через wrapper
3. **Мониторить** через `run_summary.json` и `progress.jsonl`
4. **Обработать REVIEW** результаты после завершения
5. **Интеграция в Celery** — перенести логику `auto_enrich.py` в Celery-задачу для полной оркестрации через Laravel Scheduler (задача H12 в бэклоге)
