# Sprint 4 — Продакшен, Event Harvesting, интеграция с Laravel

- **Дата:** 2026-02-24
- **Git commit:** 5110c01 (uncommitted Sprint 4 changes on top)
- **Область:** `ai-pipeline/harvester/` — config, metrics, strategies, api, workers, enrichment
- **Источник истины:** `docs/Harvester_v1_Development_Plan.md`, `docs/Navigator_Core_Model_and_API.md`

---

## 1. Цель спринта

**DoD по плану:** Все org_website обработаны; результаты в staging Core; пороги и мониторинг согласованы. Для пилотной выборки сайтов собраны мероприятия.

**Факт:** реализованы все инфраструктурные компоненты Sprint 4:
- Structured logging (structlog) с JSON/console форматом
- Centralized metrics collector (HarvestMetrics)
- Firecrawl Cloud fallback для SPA/Cloudflare-защищённых сайтов
- Event harvesting: discovery + classification через EventProcessor
- HTTP API для интеграции с Laravel Scheduler (FastAPI)
- URL-валидация перед краулингом
- 56 новых тестов (итого 243)

**Ожидает от тебя:** запуск полного прохода (4.6) и анализ результатов (4.7) — инструментарий готов.

---

## 2. Выполненные задачи

### 2.1. Structured logging — ГОТОВ (задача 4.1)

**Файл:** `config/logging.py`

Переход со stdlib `logging` на `structlog` во всех модулях пайплайна.

| Аспект | Реализация |
|--------|------------|
| Формат | `HARVESTER_LOG_FORMAT=json` (продакшен) или `console` (разработка) |
| Уровень | `HARVESTER_LOG_LEVEL=INFO` (по умолчанию) |
| Процессоры | contextvars, logger_name, log_level, timestamps ISO, stack traces |
| Noisy loggers | httpx, httpcore, crawl4ai, playwright, openai → WARNING |
| API | `get_logger(__name__)` — drop-in замена `logging.getLogger` |

**Обновлённые модули:**
- `processors/organization_processor.py`, `deepseek_client.py`, `event_processor.py`
- `strategies/multi_page.py`, `css_strategy.py`, `site_extractors/__init__.py`
- `core_client/api.py`
- `enrichment/dadata_client.py`
- `workers/tasks.py`
- `scripts/run_single_url.py`, `batch_test.py`

Все модули используют `structlog.get_logger(__name__)`. Для tenacity `before_sleep_log` (требует stdlib logger) сохранён fallback `_stdlib_logger`.

### 2.2. Metrics collector — ГОТОВ (задача 4.3)

**Файл:** `metrics/collector.py`

`HarvestMetrics` — thread-safe аккумулятор метрик для batch-прогонов:

| Метрика | Описание |
|---------|----------|
| Success/error count | По URL |
| Decision distribution | accepted / rejected / needs_review |
| Confidence stats | avg, min, max |
| Token usage | input, output, cache hits |
| Cost estimation | DeepSeek pricing ($0.014/M input, $0.28/M output) |
| Venue geocoding | total / geocoded / rate |
| Timing by stage | crawl, classify, enrich, core (avg per URL) |

**API:**
- `record_url_result(dict)` — записать результат одного URL
- `summary() → dict` — JSON-сериализуемая сводка
- `log_summary()` — structured log с ключевыми метриками

Thread-safe через `threading.Lock` для использования в Celery workers.

### 2.3. Firecrawl Cloud fallback — ГОТОВ (задача 4.5, H3)

**Файл:** `strategies/firecrawl_strategy.py`

`FirecrawlClient` — async HTTP-клиент для Firecrawl Cloud API:

| Свойство | Значение |
|----------|----------|
| API | POST https://api.firecrawl.dev/v1/scrape |
| Формат | markdown (onlyMainContent: true) |
| Retry | 2 попытки, exponential backoff |
| Timeout | 60s |
| Стоимость | ~$16/мес (Hobby plan) |

**Интеграция:**
- `multi_page.py`: если Crawl4AI не загрузил главную страницу И `firecrawl_fallback=True` → автоматическая попытка через Firecrawl
- CLI: `--firecrawl` — использовать Firecrawl вместо Crawl4AI для основного crawl
- Graceful degradation: если `FIRECRAWL_API_KEY` не установлен — fallback не используется, пайплайн работает как раньше

**Закрывает:** H3 (Sprint 1.10: orateatr.com — SPA не загружается Playwright)

### 2.4. Event Harvesting — ГОТОВ (задача 4.8)

**Файлы:**
- `strategies/event_discovery.py` — обнаружение и разбор event-страниц
- `workers/tasks.py` — Celery task `harvest_events`
- `scripts/run_single_url.py` — CLI flag `--harvest-events`

**Архитектура: Variant C (cached-hybrid)**

```
Organization crawl (multi_page.py)
  │
  ├── /news, /afisha, /events → FILTERED OUT (не входят в org-merge, правильно)
  │
  └── [main + /kontakty + /o-nas + /uslugi + /rekvizity] → OrganizationProcessor
      
Event discovery (event_discovery.py)
  │
  ├── Find event pages: 9 паттернов + ссылки из markdown главной
  │
  ├── Crawl /news, /afisha (до 3 страниц)
  │
  ├── Split: markdown → individual EventCandidate entries
  │   ├── По заголовкам ## / ###
  │   ├── Фильтр: irrelevant (тендеры, вакансии, закупки)
  │   ├── Фильтр: freshness ≤ 60 дней
  │   └── Фильтр: event keywords (масленица, мастер-класс, концерт, школа ухода...)
  │
  └── Classify each candidate via EventProcessor + DeepSeek → EventOutput
```

**EventDiscoverer:**

| Параметр | Значение |
|----------|----------|
| max_event_pages | 3 (crawl до 3 /news-подобных страниц) |
| max_events_per_page | 10 (не более 10 кандидатов с одной страницы) |
| freshness_days | 60 (игнорировать записи старше 2 месяцев) |
| EVENT_PAGE_PATTERNS | 9 паттернов: /news, /novosti, /afisha, /events, /meropriyatiya, /announcements, /anonsy, /press, /sobytiya |
| EVENT_KEYWORDS | 28 ключевых слов (масленица, мастер-класс, концерт, 55+, серебряный возраст, школа ухода...) |
| IRRELEVANT_MARKERS | тендер, закупки, вакансии, протокол |

**CLI:**
```bash
# Обнаружить и классифицировать мероприятия с сайта
python -m scripts.run_single_url https://kcson-vologda.gov35.ru --harvest-events --pretty
```

**Celery:**
```python
from workers.tasks import harvest_events
harvest_events.delay(url="https://kcson-vologda.gov35.ru", send_to_core=True)
```

**Инвариант:** /news markdown НЕ включается в org-merge для OrganizationProcessor — это правильно, шум от новостей размывает classification организации. Мероприятия всегда обрабатываются отдельным EventProcessor.

### 2.5. Harvest Trigger API — ГОТОВ (задача 4.4)

**Файл:** `api/harvest_api.py`

FastAPI HTTP-сервер для интеграции с Laravel Scheduler:

| Endpoint | Метод | Назначение |
|----------|-------|-----------|
| `/harvest/run` | POST | Dispatch batch: список source URLs → Celery group |
| `/harvest/events` | POST | Dispatch event harvesting для списка URL |
| `/harvest/status/{task_id}` | GET | Проверить статус Celery task |
| `/health` | GET | Health check |

**Request: POST /harvest/run:**
```json
{
  "sources": [
    {"url": "https://kcson.ru", "source_id": "uuid-1"},
    {"url": "https://fond.ru", "source_id": "uuid-2"}
  ],
  "multi_page": true,
  "enrich_geo": true,
  "send_to_core": true
}
```

**Запуск:**
```bash
uvicorn api.harvest_api:app --host 0.0.0.0 --port 8100
```

**Опционально:** `HARVESTER_API_TOKEN` для Bearer-авторизации.

### 2.6. URL-валидация — ГОТОВ (задача 4.2)

**Файл:** `enrichment/url_validator.py`

Предварительная валидация URL перед краулингом. Закрывает проблему из Sprint 3.6: 2 из 5 ошибок были вызваны невалидными URL в БД.

| Проверка | Пример |
|----------|--------|
| Empty URL | `""` → rejected |
| Missing scheme | `example.com` → rejected |
| No hostname | `https://` → rejected |
| No TLD | `https://localhost` → rejected |
| Truncated domain | `mikh-kcson.ryazan.` → rejected |

Интеграция: `process_batch` в Celery предварительно фильтрует невалидные URL с логированием.

---

## 3. Тесты

| Файл | Тестов | Что покрывает |
|------|--------|---------------|
| `tests/test_metrics_collector.py` | 11 | HarvestMetrics: accumulation, cost, thread safety |
| `tests/test_url_validator.py` | 14 | URL validation, filter_valid_urls |
| `tests/test_event_discovery.py` | 14 | Event page discovery, heading split, keywords, freshness, cached markdown |
| `tests/test_firecrawl_strategy.py` | 7 | FirecrawlClient: disabled mode, metrics, scrape results |
| `tests/test_harvest_api.py` | 6 | FastAPI endpoints: health, run, status |
| `tests/test_logging_config.py` | 4 | structlog configure, get_logger |
| **Итого Sprint 4** | **56** | |
| **Всего в проекте** | **243** | Все проходят (`pytest -v`, 2.5s) |

---

## 4. Архитектура после Sprint 4

```
                    ┌─────────────────────────────────────┐
                    │  Laravel Scheduler / Manual trigger  │
                    └───────────────┬─────────────────────┘
                                    │ POST /harvest/run
                                    ▼
                    ┌───────────────────────────────────┐
                    │   api/harvest_api.py (FastAPI)    │  ← [NEW]
                    │   POST /harvest/run               │
                    │   POST /harvest/events            │
                    │   GET  /harvest/status/{id}       │
                    └───────────────┬───────────────────┘
                                    │ Celery dispatch
                    ┌───────────────┼───────────────────┐
                    ▼               ▼                   ▼
         crawl_and_enrich    harvest_events ← [NEW]  process_batch
              │                    │
              ▼                    ▼
    ┌─────────────────┐   ┌──────────────────┐
    │  multi_page.py  │   │ event_discovery  │  ← [NEW]
    │  ┌────────────┐ │   │ find /news pages │
    │  │ Crawl4AI   │ │   │ split into items │
    │  ├────────────┤ │   │ filter: fresh,   │
    │  │ Firecrawl  │ │   │ keywords         │
    │  │ fallback   │ │   └────────┬─────────┘
    │  └────────────┘ │            │
    └────────┬────────┘            ▼
             │              EventProcessor
             ▼              + DeepSeek
    OrganizationProcessor          │
    + DeepSeek                     ▼
             │              to_event_payload()
             ▼                     │
    to_core_import_payload()       ▼
             │              Core: POST /import/event
             ▼
    Core: POST /import/organizer

    ────── Logging & Metrics ──────
    config/logging.py (structlog)      ← [NEW]
    metrics/collector.py               ← [NEW]
    enrichment/url_validator.py        ← [NEW]
```

---

## 5. Что НЕ вошло в Sprint 4 (ожидает)

| # | Задача | Причина | Когда |
|---|--------|---------|-------|
| 4.6 | Первый полный проход (~5 000 URL) | Требует: запущенный Redis, ключ DeepSeek, доступ к Core API или mock mode. Инструментарий готов | После предоставления ключей и запуска инфраструктуры |
| 4.7 | Анализ результатов, калибровка порогов | Зависит от 4.6 | После полного прохода |
| H4 | `suggested_taxonomy` пустой | Донастройка few-shot примеров | Backlog |
| H5 | `org_type_codes` пустой для НКО | Добавить код НКО + few-shot | Backlog |
| H8 | Few-shot пример rejected-организации | Донастройка промптов | Backlog |
| B1-B3 | Миграции source_reference + дедупликация | Laravel: PHP-миграции | До полного прохода |
| B4 | Миграция short_title | Laravel | Backlog |
| B5 | vk_group_url → vk_group_id | Laravel ImportController | Backlog |
| B11 | ImportController: fias_level, city_fias_id | Laravel ImportController | Backlog |

---

## 6. Предложения по доработке

### 6.1. Немедленно (для запуска полного прохода 4.6)

1. **Миграции B1-B3** — критически важны для дедупликации при batch-прогоне 5 000 URL
2. **Redis** — `docker compose up -d redis` или Homebrew
3. **Ключ DeepSeek** — в `.env`
4. **Core API URL** (опционально) — или mock mode
5. Запуск: `uvicorn api.harvest_api:app --port 8100` + `celery -A workers.celery_app worker --concurrency=6`
6. Dispatch: `POST /harvest/run` с 5 000 URL из Core

### 6.2. Event harvesting: пилотный тест

Рекомендую пилот на 10-20 сайтах socinfo.ru КЦСОН:
```bash
python -m scripts.run_single_url https://irkcson.aln.socinfo.ru --harvest-events --pretty
```

Ожидаемый результат: 3-10 мероприятий с каждого сайта (масленицы, мастер-классы, школы ухода), acceptance rate ~60-70% (мероприятия профильнее, чем организации).

### 6.3. Docker-compose: добавить API сервис

```yaml
  harvester-api:
    build:
      context: .
      target: worker
    command: uvicorn api.harvest_api:app --host 0.0.0.0 --port 8100
    ports:
      - "8100:8100"
    env_file: .env
    depends_on:
      redis:
        condition: service_healthy
```

### 6.4. Flower для мониторинга

Добавить в docker-compose:
```yaml
  flower:
    build:
      context: .
      target: worker
    command: celery -A workers.celery_app flower --port=5555
    ports:
      - "5555:5555"
    depends_on:
      redis:
        condition: service_healthy
```

---

## 7. Структура файлов после Sprint 4

```
ai-pipeline/harvester/
├── api/                           ← [NEW]
│   ├── __init__.py
│   └── harvest_api.py                 FastAPI: /harvest/run, /harvest/events, /harvest/status
├── config/
│   ├── logging.py                 ← [NEW] structlog configuration
│   ├── settings.py                (без изменений)
│   ├── seeders.py                 (без изменений)
│   └── llm_config.py             (без изменений)
├── metrics/                       ← [NEW]
│   ├── __init__.py
│   └── collector.py                   HarvestMetrics: thread-safe accumulator
├── strategies/
│   ├── multi_page.py              ← [UPDATED] Firecrawl fallback integration
│   ├── firecrawl_strategy.py      ← [NEW] FirecrawlClient for SPA/Cloudflare sites
│   ├── event_discovery.py         ← [NEW] EventDiscoverer: /news → event candidates
│   ├── css_strategy.py            (structlog update)
│   ├── site_extractors/           (structlog update)
│   │   ├── __init__.py
│   │   └── socinfo.py
│   ├── strategy_router.py         (без изменений)
│   └── regex_strategy.py          (без изменений)
├── processors/
│   ├── organization_processor.py  ← [UPDATED] structlog
│   ├── event_processor.py         ← [UPDATED] structlog
│   └── deepseek_client.py         ← [UPDATED] structlog
├── enrichment/
│   ├── dadata_client.py           ← [UPDATED] structlog
│   └── url_validator.py           ← [NEW] URL validation before crawl
├── core_client/
│   └── api.py                     ← [UPDATED] structlog
├── workers/
│   ├── celery_app.py              ← [UPDATED] harvest_events routing
│   └── tasks.py                   ← [UPDATED] structlog, harvest_events task, URL validation
├── scripts/
│   ├── run_single_url.py          ← [UPDATED] --harvest-events, --firecrawl flags
│   └── batch_test.py              ← [UPDATED] structlog
├── tests/
│   ├── test_metrics_collector.py  ← [NEW] 11 тестов
│   ├── test_url_validator.py      ← [NEW] 14 тестов
│   ├── test_event_discovery.py    ← [NEW] 14 тестов
│   ├── test_firecrawl_strategy.py ← [NEW] 7 тестов
│   ├── test_harvest_api.py        ← [NEW] 6 тестов
│   ├── test_logging_config.py     ← [NEW] 4 тестов
│   └── (existing: 187 тестов)
├── pyproject.toml                 ← [UPDATED] +fastapi, +uvicorn, +metrics, +api packages
└── (docs/, schemas/, prompts/ — без изменений)
```

---

## 8. Запуск и проверка

### Тесты
```bash
cd ai-pipeline/harvester
python -m pytest tests/ -v  # 243 tests, ~2.5s
```

### CLI: event harvesting
```bash
python -m scripts.run_single_url https://kcson-vologda.gov35.ru --harvest-events --pretty
```

### CLI: Firecrawl crawl
```bash
FIRECRAWL_API_KEY=xxx python -m scripts.run_single_url https://spa-site.com --firecrawl --pretty
```

### API server
```bash
uvicorn api.harvest_api:app --host 0.0.0.0 --port 8100
# POST http://localhost:8100/harvest/run с телом {"sources": [...]}
# POST http://localhost:8100/harvest/events с телом {"urls": [...]}
```

### Full stack (Docker)
```bash
docker compose up -d redis harvester-worker
# + uvicorn в отдельном контейнере (см. §6.3)
```
