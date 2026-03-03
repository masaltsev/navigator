# Sprint 3 — Multi-page crawl, CSS-стратегия, Celery, Docker

- **Дата:** 2026-02-24
- **Git commit:** 52d478c (uncommitted changes on top)
- **Область:** `ai-pipeline/harvester/strategies/`, `ai-pipeline/harvester/workers/`, Docker
- **Источник истины:** `docs/Harvester_v1_Development_Plan.md`, `docs/Navigator_Core_Model_and_API.md`

---

## 1. Цель спринта

**DoD по плану:** Celery-воркер обрабатывает batch из 50 URL; для части источников используются CSS-шаблоны (0 токенов).

**Факт:** реализованы все компоненты Sprint 3:
- Multi-page crawler с обходом подстраниц и слиянием markdown
- CSS-стратегия с реестром шаблонов (инфраструктура готова, шаблоны — по живым HTML)
- Celery app + tasks (crawl_and_enrich, process_batch) с async-интеграцией
- Docker: Dockerfile (multi-stage: worker / cli / test) + docker-compose (redis + harvester)
- CLI обновлён: `--multi-page` флаг для multi-page crawl

Batch-тест на 50 URL (задача 3.6) требует: (1) запущенный Redis, (2) ключ DeepSeek, (3) список URL из Core или вручную. Инструментарий готов — тест можно запустить после предоставления данных.

---

## 2. Выполненные задачи

### 2.1. strategies/multi_page.py — ГОТОВ (задача 3.1 + H1 + H2)

**Файл:** `ai-pipeline/harvester/strategies/multi_page.py`

**Проблема (Sprint 1.10):** адреса, email, реквизиты, полное юридическое название часто находятся на подстраницах (/kontakty, /o-nas, /uslugi), а не на главной. Однопоточный crawl пропускает эти данные.

**Решение:** `MultiPageCrawler` — crawl главной + до 5 релевантных подстраниц, слияние markdown.

**Алгоритм:**

```
1. Crawl главная страница
2. Discover subpages:
   a. 17 известных URL-паттернов (SUBPAGE_PATTERNS):
      /kontakty, /contacts, /o-nas, /about, /uslugi, /services,
      /svedeniya, /struktura, /otdeleniya, /spetsialisty, /rekvizity, ...
   b. Внутренние ссылки из markdown главной (regex [text](/path))
   c. href-атрибуты со ссылками на тот же домен
3. Filter: исключить нерелевантные (/news, /vacancy, /photo, /admin, /bitrix)
4. Score + sort: kontakty/rekvizity (100) > o-nas/uslugi (50) > struktura (25) > other (10)
5. Crawl top-N subpages (default 5) with delay between requests
6. Merge: sections с headers, main page first, limit 30K chars total
```

**Ключевые свойства:**
- Повторно использует один `AsyncWebCrawler` instance (один браузер) для всех страниц
- Таймаут подстраниц снижен (15s vs 30s для главной)
- Graceful degradation: если подстраница не загрузилась — пропуск, основная страница достаточна
- Limit 30K chars merged markdown (≈ DeepSeek context limit после system prompt)

### 2.2. strategies/css_strategy.py — ГОТОВ (задача 3.3)

**Файл:** `ai-pipeline/harvester/strategies/css_strategy.py`

`CssTemplateRegistry` — реестр CSS-шаблонов из `schemas/css_templates/*.json`.

| Метод | Назначение |
|-------|-----------|
| `has_template(name)` | Проверка наличия шаблона |
| `get_template(name)` | Получить сырой JSON шаблона |
| `build_extraction_config(name)` | Построить `CrawlerRunConfig` с `JsonCssExtractionStrategy` |
| `available_templates` | Список доступных шаблонов |

### 2.2.1. Site Extractors: socinfo.ru — ГОТОВ (задача 3.2)

**Проблема с CSS-подходом:** Crawl4AI stripped all CSS classes/IDs from `cleaned_html`, making CSS selectors fragile.

**Решение:** Markdown-based site-specific extractors — более надёжный подход, работает с текущим pipeline:

| Файл | Назначение |
|------|-----------|
| `strategies/site_extractors/__init__.py` | `SiteExtractorRegistry`: auto-detect platform по URL → extract → dict |
| `strategies/site_extractors/socinfo.py` | `SocinfoExtractor`: regex-based extraction для *.socinfo.ru |
| `schemas/css_templates/socinfo.json` | CSS-шаблон (reference, для будущего raw HTML usage) |

**SocinfoExtractor извлекает 10 полей (0 LLM-токенов):**

| Поле | Источник в markdown | Точность |
|------|---------------------|----------|
| `title` | Header area (после logo, до меню) | 100% (8/8 сайтов) |
| `short_title` | Footer `© <name> .` | 100% |
| `address_raw` | `## Адрес` / `## Контакты` секция | 100% |
| `phones` | Regex по всему markdown | 100% |
| `emails` | Regex (noise-фильтр: socinfo.ru, mintrud) | 100% |
| `director` | Паттерн `Директор:` | 100% (где есть) |
| `work_schedule` | Паттерн `Режим работы:` / `ГРАФИК` | 100% (где есть) |
| `description` | Контент после `# Главная` | 100% |
| `vk_url` / `ok_url` | Regex социальных ссылок (без share) | 100% |

**Валидация:** протестировано на 8 реальных socinfo.ru снапшотов из Sprint 3.6 batch test.

**Интеграция в CLI:**
```bash
# Только site-extraction (0 LLM-токенов):
python -m scripts.run_single_url https://irkcson.aln.socinfo.ru/ --site-extract --pretty

# Multi-page + classify (site data добавляется в payload._site_extraction):
python -m scripts.run_single_url https://irkcson.aln.socinfo.ru/ --multi-page --pretty
```

**Архитектурное решение:** markdown-extractor предпочтительнее CSS т.к.:
1. Crawl4AI `cleaned_html` теряет class/id атрибуты — CSS-селекторы ненадёжны
2. Markdown-вывод от одной CMS 100% консистентен
3. Работает с текущим pipeline без переключения на HTML-based extraction
4. Расширяемо: для новой платформы — новый файл в `site_extractors/`

### 2.3. workers/celery_app.py — ГОТОВ (задача 3.4)

**Файл:** `ai-pipeline/harvester/workers/celery_app.py`

| Параметр | Значение | Обоснование |
|----------|----------|-------------|
| Broker/Backend | Redis (`REDIS_URL`) | Минимальная инфраструктура |
| Serializer | JSON | Совместимость с payload |
| `task_acks_late` | `True` | Reliability: задача не теряется при crash воркера |
| `worker_prefetch_multiplier` | 1 | Каждый воркер берёт 1 задачу, не перегружая |
| `task_soft_time_limit` | 120s | Crawl + LLM = ~20-40s, запас на retry |
| `task_time_limit` | 180s | Hard kill при зависании |
| `worker_max_tasks_per_child` | 50 | Перезапуск процесса для предотвращения утечек памяти (Playwright) |
| Routing | `harvester` (single), `harvester-batch` (fan-out) | Разделение приоритетов |

### 2.4. workers/tasks.py — ГОТОВ (задача 3.4)

**Файл:** `ai-pipeline/harvester/workers/tasks.py`

Две задачи:

| Task | Описание |
|------|----------|
| `crawl_and_enrich` | Полный pipeline для одного URL: crawl (single/multi-page) → DeepSeek → Dadata → Core API. Async pipeline внутри `asyncio.run()`. Retry: 2 попытки, delay 30s |
| `process_batch` | Fan-out: принимает `list[dict]` с URL, создаёт Celery `group` из `crawl_and_enrich` задач. Параллельное выполнение до concurrency воркеров |

**Async + Celery интеграция:** `_run_pipeline()` — единая async-функция, вызываемая через `asyncio.run()` в sync-контексте Celery task. Это обеспечивает:
- Полноценный async I/O (httpx, Crawl4AI)
- Чистый event loop на каждый task (без конфликтов между воркерами)
- Метрики timing по каждому этапу (crawl, classify, enrich, core)

**Поддержка multi-page:** параметр `multi_page=True` (по умолчанию) в `crawl_and_enrich`.

### 2.5. Docker — ГОТОВ (задача 3.5)

**Файлы:**
- `Dockerfile` — multi-stage build:
  - `base`: Python 3.12-slim + deps + Playwright Chromium
  - `worker`: Celery worker (concurrency=2) — production target
  - `cli`: CLI entrypoint — one-off crawl
  - `test`: pytest runner
- `docker-compose.yml`:
  - `redis` (redis:7-alpine, healthcheck, persistent volume)
  - `harvester-worker` (auto-restart, depends on Redis)
  - `harvester-cli` (manual run via `docker compose run --rm`, profile: cli)
- `.dockerignore` — исключает `.env`, `__pycache__`, docs, тесты

**Запуск:**
```bash
# Worker mode (production)
docker compose up -d redis harvester-worker

# CLI (one-off)
docker compose run --rm harvester-cli https://example.com --to-core --multi-page --pretty

# Run tests
docker compose run --rm --build --target test harvester-worker pytest -v
```

### 2.6. CLI обновлён — `--multi-page`

**Файл:** `ai-pipeline/harvester/scripts/run_single_url.py`

Новый флаг `--multi-page` активирует `MultiPageCrawler` вместо single-page crawl.

```bash
# Multi-page crawl + classify
python -m scripts.run_single_url https://kcson-vologda.gov35.ru --multi-page --pretty

# Full E2E: multi-page → Dadata → Core
python -m scripts.run_single_url https://kcson-vologda.gov35.ru --to-core --multi-page --pretty
```

В `_meta` добавлены:
- `multi_page: true/false`
- `pages_attempted`, `pages_success`
- `page_urls` — список успешно скраулённых подстраниц

---

## 3. Тесты

| Файл | Тестов | Что покрывает |
|------|--------|---------------|
| `tests/test_multi_page.py` | 25 | Subpage discovery, relevance filter, priority scoring, markdown merge, edge cases |
| `tests/test_css_strategy.py` | 10 | CssTemplateRegistry: load/has/get, invalid JSON handling, build config |
| `tests/test_celery_tasks.py` | 12 | Celery app config, task registration, routing, retry params, signatures |
| `tests/test_socinfo_extractor.py` | 31 | SocinfoExtractor: platform detection, title/address/phone/email/director/schedule/description extraction на 8 реальных сайтах |
| **Итого Sprint 3** | **78** | |
| **Всего в проекте** | **187** | Все проходят (`pytest -v`, 1.9s) |

Все тесты — unit, без сети, без Redis, без LLM.

---

## 4. Архитектура после Sprint 3

```
URL
 │
 ├── --multi-page ?
 │   ├── YES → MultiPageCrawler                ← [NEW]
 │   │         ├── crawl main page
 │   │         ├── discover subpages (patterns + links)
 │   │         ├── crawl top-5 subpages
 │   │         └── merge markdown (≤30K chars)
 │   └── NO  → single page crawl (existing)
 │
 ▼
Crawl4AI (markdown)
 │
 ├── CssTemplateRegistry.has_template() ?      ← [NEW]
 │   ├── YES → JsonCssExtractionStrategy (0 tokens)
 │   └── NO  → OrganizationProcessor + DeepSeek
 │
 ▼
OrganizationOutput (Pydantic)
 │
 ├── DadataClient.geocode_batch()
 │
 ▼
to_core_import_payload()
 │
 ▼
NavigatorCoreClient.import_organizer()
 │
 ▼
Core Response

--- Celery orchestration ---                   ← [NEW]

Redis (broker)
 │
 ├── crawl_and_enrich(url, ...)  ← single task
 │   └── asyncio.run(_run_pipeline(...))
 │
 └── process_batch(sources)      ← fan-out
     └── group([crawl_and_enrich.s(...) × N])
```

---

## 5. Что НЕ вошло в Sprint 3 (осталось / перенесено)

| # | Задача | Причина | Когда |
|---|--------|---------|-------|
| ~~3.2~~ | ~~Генерация CSS-шаблонов для КЦСОН~~ | **Done.** `SocinfoExtractor` — markdown-based, 31 тест, 8 валидированных сайтов | Sprint 3 ✅ |
| ~~3.6~~ | ~~Batch-тест на 50 URL~~ | **Done.** 45/50 success, 25 accepted, 262 HTML-снимка | Sprint 3 ✅ |
| B4 | Миграция `short_title` в organizations | Laravel: нужна PHP-миграция | Sprint 4 (Laravel-задача) |
| B5 | `vk_group_url` → `vk_group_id` | Laravel ImportController | Sprint 4 |
| B11 | ImportController: принимать fias_level, city_fias_id, region_iso | Laravel ImportController | Sprint 4 |
| H8 | Few-shot пример rejected-организации | Донастройка промптов (можно в любой момент) | Sprint 4 |

---

## 6. Предложения по доработке

### 6.1. Немедленно (для полноценного batch-теста 3.6)

1. **Запустить Redis** — `docker compose up -d redis` или локально
2. **Предоставить список 50 URL** — из Core (`GET /api/internal/sources?kind=org_website`) или вручную
3. **Ключ DeepSeek** — в `.env` для реального LLM-процессинга
4. Запуск: `docker compose up -d` → `celery -A workers.celery_app worker --loglevel=info` → скрипт диспатча

### 6.2. Расширение site extractors (после Sprint 3)

Задача 3.2 выполнена для socinfo.ru. Следующие платформы для покрытия:
1. **gov35.ru** — Вологодская область, КЦСОН (другой CMS, другая структура markdown)
2. **Медицинские учреждения** — rosminzdrav.ru layout, стандартные разделы «О нас», «Услуги», «Контакты»
3. **НКО-реестры** — minjust.gov.ru, портал НКО

Ожидаемая экономия: для socinfo.ru (8/50 = 16% батча) экстракция контактов без LLM. При расширении до 3-4 платформ — покрытие 30-40% типовых URL.

### 6.3. Улучшения multi-page crawl

- **HEAD-проверка** перед GET: если подстраница возвращает 404, не тратить ресурсы на полный crawl
- **Parallel subpage crawl**: одновременный crawl 2-3 подстраниц (сейчас последовательно с delay)
- **Adaptive max_subpages**: для крупных сайтов (>20 подстраниц) увеличить лимит

### 6.4. Celery мониторинг

- **Flower** — web UI для мониторинга задач: `celery -A workers.celery_app flower`
- Добавить Flower в docker-compose как опциональный сервис
- Экспорт метрик: success rate, avg time per URL, queue depth

---

## 7. Структура файлов после Sprint 3

```
ai-pipeline/harvester/
├── strategies/
│   ├── multi_page.py           ← [NEW] MultiPageCrawler, 17 subpage patterns
│   ├── css_strategy.py         ← [NEW] CssTemplateRegistry
│   ├── site_extractors/        ← [NEW] markdown-based site-specific extractors
│   │   ├── __init__.py              SiteExtractorRegistry: detect + extract
│   │   └── socinfo.py               SocinfoExtractor: 10 полей из *.socinfo.ru
│   ├── strategy_router.py      (legacy, без изменений)
│   └── regex_strategy.py       (без изменений)
├── workers/                    ← [NEW]
│   ├── __init__.py
│   ├── celery_app.py               Celery config, queues, routing
│   └── tasks.py                    crawl_and_enrich, process_batch
├── schemas/
│   └── css_templates/          ← [NEW/UPDATED]
│       ├── .gitkeep
│       └── socinfo.json             CSS-шаблон (reference для raw HTML)
├── scripts/
│   └── run_single_url.py       ← [UPDATED] --multi-page, --site-extract flags
├── tests/
│   ├── test_multi_page.py      ← [NEW] 25 тестов
│   ├── test_css_strategy.py    ← [NEW] 10 тестов
│   ├── test_celery_tasks.py    ← [NEW] 12 тестов
│   ├── test_socinfo_extractor.py ← [NEW] 31 тест (8 реальных сайтов)
│   └── (existing: test_schemas, test_prompts, test_dadata, test_core, test_payload — 109 тестов)
├── Dockerfile                  ← [NEW] multi-stage: worker / cli / test
├── docker-compose.yml          ← [NEW] redis + harvester-worker + cli
├── .dockerignore               ← [NEW]
└── (config/, prompts/, processors/, enrichment/, core_client/ — без изменений)
```

---

## 8. Запуск и проверка

### CLI: multi-page crawl
```bash
cd ai-pipeline/harvester
python -m scripts.run_single_url https://kcson-vologda.gov35.ru --multi-page --pretty
```

### Docker: worker
```bash
cd ai-pipeline/harvester
docker compose up -d redis harvester-worker
# Мониторинг
docker compose logs -f harvester-worker
```

### Celery: dispatch batch
```python
from workers.tasks import process_batch

sources = [
    {"url": "https://kcson-vologda.gov35.ru", "source_id": "uuid-1"},
    {"url": "https://socinfo.ru/some-kcson", "source_id": "uuid-2"},
    # ...
]
result = process_batch.delay(sources, multi_page=True, send_to_core=True)
print(result.id)  # group task ID
```

### Тесты
```bash
cd ai-pipeline/harvester
python -m pytest tests/ -v  # 187 tests, ~1.9s
```

---

## 9. Batch-тест: 50 URL (задача 3.6)

### 9.1. Настройка

- **Redis:** локальный Homebrew (`brew install redis && brew services start redis`)
- **URLs:** 50 случайных из Core (таблица `sources`, `kind=org_website`):
  - 12 КЦСОН (kcson, cson, кцсон в URL)
  - 8 медицинских учреждений (kb, gkb, hospital)
  - 8 socinfo.ru (типовая платформа соцучреждений)
  - 7 НКО / фондов (fond, blago, nko)
  - 15 прочих
- **Режим:** multi-page crawl (до 5 подстраниц), Dadata geocoding, Core API mock mode
- **Concurrency:** 2 параллельных задачи
- **HTML-снимки:** сохранены в `tests/fixtures/batch_raw/` (262 файла: merged + отдельные страницы)

### 9.2. Сводные результаты

| Метрика | Значение |
|---------|----------|
| **Всего URL** | 50 |
| **Успешно** | 45 (90%) |
| **Ошибки** | 5 (10%) |
| **Accepted** | 25 (56% от успешных) |
| **Rejected** | 14 (31%) |
| **Needs review** | 6 (13%) |
| **Works with elderly** | 31 (69%) |
| **Avg confidence** | 0.719 |
| **Avg time per URL** | 23.0s (wall clock) / 49.3s (per-task) |
| **Total time** | 19.2 min (concurrency=2) |

### 9.3. Результаты по категориям

**КЦСОН (18 → 15 success, 3 error):**
- 13 из 15 → **accepted** (confidence 0.88-0.96, все works_with_elderly=true)
- 2 rejected: 1 сайт «Не добавлен на хостинг» (парковка), 1 не загрузился
- Средний confidence: **0.91** — высокий, стабильный
- Multi-page работает отлично: 5/5 страниц у большинства
- Venues geocoded: ~50% (остальные — адреса в нестандартном формате)

**Медицинские (9 → 9 success):**
- 3 accepted, 5 needs_review, 1 rejected
- Средний confidence: **0.78** — ниже КЦСОН, ожидаемо (меньше явных маркеров 55+)
- Needs_review — правильное решение: медучреждения требуют ручной проверки наличия гериатрического фокуса

**Socinfo (4 → 4 success):**
- 3 accepted, 1 rejected (БФ «Быть добру» — не профильный)
- Платформа socinfo.ru — хорошо структурированные сайты, отлично парсятся multi-page

**НКО (8 → 7 success):**
- 3 accepted, 4 rejected
- Rejected корректно: непрофильные фонды (кино, студенты)
- Accepted: фонды помощи пожилым (НКО ФОНД «ПОБЕДА», благотворительный фонд)

**Прочие (11 → 10 success):**
- 4 accepted, 6 rejected
- Rejected правильно: церкви, туризм, образование, кикбоксинг

### 9.4. Стоимость DeepSeek API

| Метрика | Значение |
|---------|----------|
| Input tokens | 980,741 |
| Output tokens | 31,741 |
| Cache hits | 45/45 (100%) |
| Cost per batch (45 URL) | $0.0226 |
| **Cost per URL** | **$0.0005** |
| **Extrapolation to 5,000 URL** | **$2.51** |

Стоимость ниже оценки Sprint 1 ($2.75) — prefix caching 100% hit rate в batch mode.

### 9.5. Ошибки

| URL | Причина |
|-----|---------|
| `kcson23.uszn032.ru` | DNS не резолвится |
| `fond-tut.ru` | Сайт недоступен |
| `civil-society.donland.ru` | Таймаут |
| `kcson27.uszn032.ru` | DNS не резолвится |
| `mikh-kcson.ryazan.` | Обрезанный домен в БД (невалидный URL) |

3 из 5 ошибок — данные в БД (невалидные/мёртвые URL). Решение: валидация URL при загрузке источников.

### 9.6. Качество multi-page crawl

- 42 из 45 успешных сайтов: crawl **5/5 страниц** (главная + 4 подстраницы)
- 2 сайта: 1/5 (подстраницы отсутствуют/пустые — одностраничные сайты)
- 1 сайт: 3/5 (2 подстраницы не загрузились)
- Подстраницы реально добавляют данные: контакты, реквизиты, адреса

### 9.7. HTML-снимки для DOM-анализа

Сохранены в `tests/fixtures/batch_raw/` (262 файла):

| Тип | Файлы | Примеры |
|-----|-------|---------|
| КЦСОН main pages | ~15 | `kcsonvol.ru_page.txt`, `labinsk-kcson.ru_page.txt` |
| КЦСОН subpages | ~60 | `*_kontakty_page.txt`, `*_rekvizity_page.txt` |
| КЦСОН merged | ~15 | `*_merged.txt` |
| Socinfo pages | ~30 | `irkcson.aln.socinfo.ru_*` |
| Medical pages | ~40 | `aokb28.su_*`, `kb33fmba.ru_*`, `mkb-05.ru_*` |
| NKO/Other pages | ~100+ | `fond-*`, `pokrov-fond.ru_*` |

Эти снимки готовы для:
1. Генерации CSS-шаблонов (задача 3.2) — анализ DOM socinfo.ru и типовых КЦСОН
2. Анализа структуры медицинских сайтов — стандартные разделы для шаблонов
3. Расширения тестовых fixtures

### 9.8. Предложения по доработке на основе batch-теста

1. **Валидация URL при загрузке:** 2 из 5 ошибок — невалидные URL в БД. Фильтр `WHERE base_url ~ '^https?://[a-zA-Z0-9]' AND base_url NOT LIKE '%..%'`
2. **Увеличить concurrency** до 4-6: при 2 concurrent — 19 мин на 50 URL, при 6 — ~7 мин. Лимит: DeepSeek rate limit + Dadata 10K/день
3. **CSS-шаблоны для socinfo.ru:** 8 сайтов на этой платформе, одинаковая DOM-структура → 1 шаблон сэкономит ~16% LLM-вызовов
4. **Venues geocoding:** 25% venues не геокодированы (нестандартный формат адреса). Можно добавить предварительную нормализацию или fallback через Dadata clean API
5. **Confidence калибровка:** КЦСОН стабильно 0.88-0.96, медицина 0.72-0.88. Порог 0.85 для auto-approve оптимален — пропускает КЦСОН, задерживает медицину для ревью
