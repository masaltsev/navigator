# Sprint 2 — Классификация, обогащение и Core API

- **Дата:** 2026-02-24
- **Git commit:** 52d478c (uncommitted changes on top)
- **Область:** `ai-pipeline/harvester/enrichment/`, `ai-pipeline/harvester/core_client/`, `backend/ImportController`
- **Источник истины:** `docs/Harvester_v1_Development_Plan.md`, `docs/Navigator_Core_Model_and_API.md`

---

## 1. Цель спринта

**DoD по плану:** один URL проходит полный pipeline до отправки JSON в Core API (staging).

**Факт:** полный E2E пайплайн реализован. CLI поддерживает `--to-core` (отправка в Core) и `--enrich-geo` (обогащение через Dadata). При отсутствии ключей и URL работает в mock mode.

---

## 2. Выполненные задачи

### 2.1. classifier.py → НЕ НУЖЕН

По плану Sprint 2 предполагал отдельный `enrichment/classifier.py` с fuzzy match по сидерам. В Sprint 1 архитектура изменилась: LLM классифицирует напрямую (коды справочников в системном промпте), а `OrganizationProcessor._validate_codes()` выполняет post-hoc автокоррекцию перепутанных кодов. Отдельный модуль classifier.py избыточен.

### 2.2. enrichment/dadata_client.py — ГОТОВ

**Файл:** `ai-pipeline/harvester/enrichment/dadata_client.py`

Async-клиент для Dadata API с двумя режимами:

| Режим | API | Стоимость | Качество |
|-------|-----|-----------|----------|
| **Clean** (по умолчанию при наличии `secret_key`) | `cleaner.dadata.ru` | 1 запрос = 1 ед. | Высокое: нормализация + quality code |
| **Suggest** (fallback) | `suggestions.dadata.ru` | Бесплатно (10K/день) | Среднее: автодополнение top-1 |

Ключевые свойства:
- **Suggest по умолчанию:** бесплатный лимит 10K/день (растёт с подпиской). Clean API — opt-in через `DADATA_USE_CLEAN=true` (платный, но выше accuracy + quality_code).
- **Graceful degradation:** при отсутствии `DADATA_API_KEY` все вызовы возвращают passthrough (address_raw без обогащения). Пайплайн не ломается.
- **Retry:** tenacity с exponential backoff для `ConnectError` и `TimeoutException`.
- **Метрики:** `total_calls`, `successful`, `failed`, `success_rate`, `mode`.
- **Результат:** `GeocodingResult` dataclass с `fias_id`, `geo_lat`, `geo_lon`, `region_iso`, `quality`.

### 2.3. confidence_scorer.py → НЕ НУЖЕН

`AIConfidenceMetadata` в `prompts/schemas.py` + decision routing в `OrganizationProcessor.process_and_sync()` полностью покрывают функциональность. Отдельный модуль избыточен.

### 2.4. payload_builder.py → РАСШИРЕН В СУЩЕСТВУЮЩЕМ МОДУЛЕ

`to_core_import_payload()` в `organization_processor.py` расширен:
- Принимает опциональный `geo_results: list[GeocodingResult]` для обогащения venues
- Venues теперь включают `fias_id`, `geo_lat`, `geo_lon` из Dadata (когда доступны)
- Формат payload полностью совместим с обновлённым `ImportController`

### 2.5. core_client/api.py — ГОТОВ

**Файл:** `ai-pipeline/harvester/core_client/api.py`

Async HTTP-клиент (`httpx`) для Navigator Core Internal API:

| Endpoint | Метод |
|----------|-------|
| `POST /api/internal/import/organizer` | `import_organizer(payload)` |
| `POST /api/internal/import/event` | `import_event(payload)` |
| `POST /api/internal/import/batch` | `import_batch(items)` |

**Mock mode:** при пустом `CORE_API_URL` клиент работает без сети:
- Валидирует наличие обязательных полей (`source_reference`, `title`, `ai_metadata`)
- Воспроизводит State Machine ImportController:
  - `accepted` + confidence ≥ 0.85 + elderly → `approved`
  - `accepted` + иное → `pending_review`
  - `needs_review` → `pending_review`
  - `rejected` → `rejected`
- Возвращает синтетические UUID и `_mock: true` в ответе

**Retry:** tenacity для `ConnectError`, `TimeoutException`, `ReadTimeout` (3 попытки, exponential backoff).

### 2.6. E2E: CLI расширен — ГОТОВ

**Файл:** `ai-pipeline/harvester/scripts/run_single_url.py`

Новые флаги:

| Флаг | Что делает |
|------|------------|
| `--enrich-geo` | После LLM-классификации обогащает venues через Dadata |
| `--to-core` | Полный E2E: crawl → LLM → Dadata → Core API (включает `--enrich-geo`) |
| `--check-env` | Показывает статус всех ключей (DeepSeek, Dadata, Core) |

Примеры:
```bash
# Полный E2E (mock mode без ключей)
python -m scripts.run_single_url https://kcson-vologda.gov35.ru --to-core --pretty

# Только geocoding
python -m scripts.run_single_url https://example.com --enrich-geo --pretty

# Проверка переменных окружения
python -m scripts.run_single_url --check-env
```

Payload включает `_meta` с метриками (`elapsed_classify_s`, `venues_geocoded`, `cache_hit_rate`, `estimated_cost_usd`) и `_core_response` с ответом Core API.

### 2.7. Fixtures — ГОТОВЫ

| Файл | Описание |
|------|----------|
| `tests/fixtures/kcson_vologda_markdown.txt` | Синтетический markdown КЦСОН Вологды: полная информация (услуги, контакты, реквизиты, специалисты) |
| `tests/fixtures/nko_obraz_zhizni_markdown.txt` | Синтетический markdown НКО «Образ жизни»: фонд помощи пожилым |
| `tests/fixtures/expected_payload_kcson.json` | Ожидаемый payload для КЦСОН с Dadata-enriched venue |

---

## 3. Дополнительные исправления

### 3.1. Fix target_audience validation (ImportController)

**Проблема:** валидация ImportController определяла `target_audience` как `nullable|string|max:1000`, но колонка в БД — `jsonb`, модель кастит в `array`, а Python-пайплайн отправляет массив.

**Решение:**
```php
// Было
'target_audience' => 'nullable|string|max:1000',

// Стало
'target_audience' => 'nullable|array',
'target_audience.*' => 'string',
```

Обработка упрощена: `$data['target_audience'] ?? null` (без ненужной конвертации string→array).

---

## 4. Тесты

| Файл | Тестов | Что покрывает |
|------|--------|---------------|
| `tests/test_dadata_client.py` | 14 | DadataClient: disabled/enabled, GeocodingResult, _safe_float, batch passthrough |
| `tests/test_core_client.py` | 13 | NavigatorCoreClient: mock mode (все 5 вариантов State Machine), validation, batch, metrics |
| `tests/test_payload_builder.py` | 14 | to_core_import_payload: basic fields, venue enrichment (full/partial/empty geo), nullable fields |
| **Итого Sprint 2** | **41** | |
| **Всего в проекте** | **76** | Все проходят (`pytest -v`, 0.6s) |

---

## 5. Архитектура после Sprint 2

```
URL
 │
 ▼
Crawl4AI (markdown)
 │
 ▼
OrganizationProcessor
 ├── build_organization_system_prompt()  ← справочники + правила + schema + few-shot
 ├── DeepSeekClient.classify()           ← OpenAI SDK, JSON mode, retry
 ├── _validate_codes()                   ← post-hoc автокоррекция перепутанных кодов
 │
 ▼
OrganizationOutput (Pydantic)
 │
 ├── DadataClient.geocode_batch()  ← [NEW] fias_id, coordinates для venues
 │
 ▼
to_core_import_payload()           ← [UPDATED] venues с geo, target_audience как array
 │
 ▼
NavigatorCoreClient.import_organizer()  ← [NEW] POST → ImportController → БД
 │
 ▼
Core Response: { organizer_id, entity_id, assigned_status }
```

---

## 6. Что НЕ вошло в Sprint 2 (осталось в бэклоге)

| # | Задача | Причина | Когда |
|---|--------|---------|-------|
| B4 | Миграция `short_title` в organizations | Нужна Laravel-миграция, не Python-задача | Sprint 3 |
| B5 | Конвертация `vk_group_url` → `vk_group_id` | Нужна логика парсинга VK URL в ImportController | Sprint 3 |
| B7 | `GET /api/internal/organizers` для lookup | Нужен новый endpoint в Laravel | Sprint 3 |
| H7 | Интеграционный тест с реальным DeepSeek + Core | Требует запущенный Core и ключи DeepSeek | При E2E-тестировании |
| H8 | Few-shot пример rejected-организации | Донастройка промптов | Sprint 3 |

---

## 7. Известные ограничения и несовместимости

### 7.1. Дедупликация (G1, G2, G3 — КРИТИЧНО для batch)

`ImportController::createOrUpdateOrganization` использует `inn` как ключ `updateOrCreate`. Организации без ИНН дублируются при каждом импорте. **Блокирует batch-прогон (Sprint 4).** Решение: миграция `source_reference` + fallback ключ в Laravel.

### 7.2. Поля принимаются, но не сохраняются

| Поле | Почему не сохраняется | Решение |
|------|----------------------|---------|
| `short_title` | Нет колонки в organizations | Миграция (B4) |
| `vk_group_url` | В БД `vk_group_id` (integer) | Парсинг URL → ID (B5) |
| `telegram_url` | Нет колонки | Миграция |
| `suggested_taxonomy` | Нет таблицы | `suggested_taxonomy_items` (B8) |

### 7.3. Auth на internal API (G9)

`/api/internal/*` доступен без авторизации. Для staging/dev — ок, для production нужен middleware.

---

## 8. Рекомендации к Sprint 3

1. **Multi-page crawl (H1, задача 3.1)** — ключевое улучшение качества. Сейчас адреса и контакты часто на подстраницах `/kontakty`, `/o-nas`.
2. **CSS-шаблоны (3.2, 3.3)** — для типовых сайтов (socinfo.ru) экономия на LLM-токенах.
3. **Celery (3.4)** — для batch-обработки нужна очередь. Текущий `process_batch()` последовательный.
4. **Миграция `short_title`** (B4) — минимальные усилия, сразу сохраняет полезное поле.
5. **E2E тест с реальным Core** (H7) — после п.4 можно проверить полный цикл на staging.

---

## 9. Структура файлов после Sprint 2

```
ai-pipeline/harvester/
├── enrichment/              ← [NEW]
│   ├── __init__.py
│   └── dadata_client.py         DadataClient, GeocodingResult
├── core_client/             ← [NEW]
│   ├── __init__.py
│   └── api.py                   NavigatorCoreClient, CoreApiError
├── processors/
│   ├── organization_processor.py  ← [UPDATED] to_core_import_payload с geo
│   ├── deepseek_client.py
│   └── event_processor.py
├── scripts/
│   └── run_single_url.py     ← [UPDATED] --to-core, --enrich-geo, --check-env
├── tests/
│   ├── fixtures/
│   │   ├── kcson_vologda_markdown.txt        ← [NEW]
│   │   ├── nko_obraz_zhizni_markdown.txt     ← [NEW]
│   │   ├── expected_payload_kcson.json       ← [NEW]
│   │   └── raw_kirovski*/
│   ├── test_dadata_client.py     ← [NEW] 14 тестов
│   ├── test_core_client.py       ← [NEW] 13 тестов
│   ├── test_payload_builder.py   ← [NEW] 14 тестов
│   ├── test_prompts.py           17 тестов
│   └── test_schemas.py           18 тестов
└── (config/, schemas/, strategies/, prompts/, seeders_data/ — без изменений)
```
