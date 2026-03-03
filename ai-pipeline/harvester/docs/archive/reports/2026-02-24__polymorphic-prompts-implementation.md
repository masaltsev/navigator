# Отчёт: Реализация полиморфной системы промптов Harvester v1

- **Дата:** 2026-02-24
- **Git commit:** 6ebf519 (uncommitted changes on top)
- **Область:** `ai-pipeline/harvester/prompts/`, `ai-pipeline/harvester/processors/`, `ai-pipeline/harvester/tests/`
- **Источник истины:** `docs/Harvester_Prompts_Spec.md`, `docs/harvester_v1_prompt.md`
- **Инструкция разработчика:** `/Users/masaltsev/Downloads/Dev_Readme_Cursor.md`

---

## 1. Что сделано

Реализован Python-модуль полиморфных промптов для автоматической классификации и описания организаций и мероприятий для платформы «Навигатор здорового долголетия». Модуль работает через DeepSeek API в JSON-режиме и возвращает строго типизированный вывод, валидированный Pydantic v2.

### 1.1. Созданные файлы

| Файл | Строк | Назначение |
|------|-------|------------|
| `prompts/schemas.py` | ~230 | 12 Pydantic v2 моделей: `HarvestInput`, `OrganizationOutput`, `EventOutput`, `AIConfidenceMetadata`, `OrganizationClassification`, `EventClassification`, `EventSchedule`, `ExtractedVenue`, `ExtractedContact`, `TaxonomySuggestion`, `EntityType` |
| `prompts/dictionaries.py` | ~95 | Загрузка 5 JSON-справочников из `seeders_data/`, форматирование с иерархией и keywords, `lru_cache` для детерминизма и cache hit |
| `prompts/examples.py` | ~155 | 3 few-shot примера организаций (паттерны A/B/C) + 1 пример мероприятия. Все коды верифицированы против `seeders_data/` |
| `prompts/organization_prompt.py` | ~154 | Сборка system prompt для организаций (~48K символов), `build_organization_user_message()` |
| `prompts/event_prompt.py` | ~130 | Сборка system prompt для мероприятий (~45K символов), `build_event_user_message()` |
| `processors/__init__.py` | 1 | Инициализация пакета |
| `processors/deepseek_client.py` | ~145 | `DeepSeekClient` — OpenAI-compatible обёртка, JSON mode, retry (tenacity), метрики кэширования |
| `processors/organization_processor.py` | ~195 | `OrganizationProcessor` — полный цикл с idempotency routing + `to_core_import_payload()` |
| `processors/event_processor.py` | ~155 | `EventProcessor` — аналогично для мероприятий + `to_event_payload()` |
| `tests/test_schemas.py` | ~165 | 18 тестов на Pydantic-модели |
| `tests/test_prompts.py` | ~85 | 17 тестов на system prompt |

### 1.2. Изменённые файлы

| Файл | Что изменено |
|------|--------------|
| `pyproject.toml` | Добавлена зависимость `openai>=1.0`; пакет `processors` в hatch build targets |
| `prompts/__init__.py` | Обновлён docstring с перечислением публичного API и legacy-модулей |

### 1.3. Не тронуты (сохранена обратная совместимость)

- `prompts/base_system_prompt.py` — legacy-промпт для Crawl4AI extraction strategy
- `prompts/prompt_registry.py` — legacy-реестр, используется `strategy_router.py`
- `schemas/extraction.py` — `RawOrganizationData`, используется `strategy_router.py`
- `schemas/navigator_core.py` — контракт с Navigator Core API
- `config/seeders.py` — загрузка справочников для legacy-пайплайна
- `strategies/strategy_router.py` — маршрутизатор CSS/LLM стратегий

---

## 2. Архитектура модуля

### 2.1. Структура system prompt (оптимизация для DeepSeek prefix caching)

```
[1. СПРАВОЧНИКИ]   ~28K символов   ← СТАТИЧНЫЙ ПРЕФИКС, кэшируется
[2. ПЕРСОНА + ПРАВИЛА]   ~4K символов   ← СТАТИЧНЫЙ
[3. JSON SCHEMA]   ~4K символов   ← СТАТИЧНЫЙ
[4. FEW-SHOT EXAMPLES]   ~8K символов   ← СТАТИЧНЫЙ
---
[5. USER MESSAGE]   ~переменный   ← ДИНАМИЧЕСКИЙ СУФФИКС, не кэшируется
```

Блоки 1–4 формируют system message, блок 5 — user message. System prompt собирается **один раз** при инициализации процессора и переиспользуется для всех вызовов API.

### 2.2. Полиморфная маршрутизация

Три паттерна фокуса внимания в зависимости от типа организации:

| Паттерн | Триггер | Фокус извлечения |
|---------|---------|-----------------|
| **A — Медицинские учреждения** | ГБУ, ГБУЗ, поликлиника, больница | Специалисты, медуслуги, ОМС vs платные |
| **B — Социальная защита** | КЦСОН, ПНИ, интернат, кризисный центр | Надомное обслуживание, патронаж, ТСР |
| **C — Активное долголетие** | ЦОСП, досуговый центр, клуб, ДК | Занятия, кружки, расписание, маркер 55+ |

### 2.3. Decision routing (idempotency)

| `existing_entity_id` | `ai_metadata.decision` | Действие |
|----------------------|------------------------|----------|
| `null` | `accepted` | CREATE organizer |
| `null` | `needs_review` | CREATE draft (pending_review) |
| `null` | `rejected` | Пропустить |
| UUID | `accepted` | UPDATE organizer |
| UUID | `needs_review` | UPDATE + флаг модерации |
| UUID | `rejected` | MARK outdated |

### 2.4. Граф зависимостей модулей

```
prompts/schemas.py          ← чистые Pydantic-модели, без зависимостей
prompts/dictionaries.py     ← читает seeders_data/*.json
prompts/examples.py         ← константы, без зависимостей
prompts/organization_prompt.py  ← dictionaries + schemas + examples
prompts/event_prompt.py         ← dictionaries + schemas + examples

processors/deepseek_client.py       ← openai SDK + tenacity + pydantic
processors/organization_processor.py ← deepseek_client + organization_prompt + dictionaries
processors/event_processor.py       ← deepseek_client + event_prompt + dictionaries
```

---

## 3. Справочники: статистика

| Справочник | Записей | Пример кодов |
|-----------|---------|--------------|
| `thematic_categories` | 27 (3 родительских + 24 дочерних) | `"3"`, `"7"`, `"24"`, `"33"` |
| `organization_types` | 20 | `"65"`, `"82"`, `"140"`, `"144"` |
| `services` | 54 | `"70"`, `"93"`, `"108"`, `"135"` |
| `specialist_profiles` | 20 | `"96"`, `"142"`, `"143"` |
| `ownership_types` | 16 | `"152"`, `"154"`, `"162"`, `"164"` |

Все коды, использованные в few-shot примерах, верифицированы — существуют в `seeders_data/`.

---

## 4. Тестирование

**35 тестов, 35 passed, 0 failed.**

### 4.1. test_schemas.py (18 тестов)

- `AIConfidenceMetadata`: валидные значения (accepted/rejected/needs_review), невалидные (`maybe`), границы score (0.0, 1.0, <0, >1)
- `OrganizationOutput`: round-trip JSON, optional-поля, idempotency-поля, taxonomy suggestion, контакты, venues
- `EventOutput`: базовая валидация, schedule с RRule
- `TaxonomySuggestion`: обязательные поля
- `ExtractedContact`: defaults

### 4.2. test_prompts.py (17 тестов)

- **Детерминизм**: `build_dictionaries_block()` возвращает идентичный результат при повторных вызовах
- **Prefix caching**: оба system prompt начинаются с блока справочников (`"=" * 60`)
- **JSON mode**: оба промпта содержат слово `json` (обязательно для DeepSeek)
- **Маршрутизация**: промпт организаций содержит паттерны A/B/C и decision rules
- **Расписание**: промпт мероприятий содержит RRule и attendance_mode правила
- **Разделение словарей**: organization и event промпты используют один и тот же `build_dictionaries_block()` (потенциальный prefix sharing при batch-обработке)

---

## 5. Адаптации относительно спецификации

| Пункт спецификации | Адаптация | Причина |
|-------------------|-----------|---------|
| `DICT_DIR = .../dictionaries/` | Заменено на `.../seeders_data/` | Данные уже хранятся в `seeders_data/`; менять — ломать `config/seeders.py` |
| Относительные импорты (`from ..prompts...`) | Flat imports (`from prompts...`) | Сложившаяся конвенция проекта: каждый модуль — top-level package |
| `response.choices.message.content` | `response.choices[0].message.content` | Баг в спецификации: `choices` — это list |
| Markdown cleanup через `split/rsplit` | Regex `_strip_markdown_fences()` | Оригинальный код возвращал list вместо string |
| Retry только на `JSONDecodeError`, `ValidationError` | Добавлены `APIConnectionError`, `APITimeoutError` | Устойчивость к транзиентным сетевым ошибкам |

---

## 6. Что НЕ входило в скоуп

1. **HTTP-вызовы к Navigator Core API** — методы `_create_organizer`, `_update_organizer` возвращают payload dict. Реальные HTTP-вызовы (POST/PATCH) — задача Sprint 2 (core_client).
2. **Интеграция с Celery** — batch-обработка реализована синхронно в `process_batch()`. Async-воркеры — отдельная задача.
3. **Кросс-источниковая дедупликация** (`find_by_business_key`) — описана в спеке (раздел 2.12.6), но не реализована.
4. **Модификация legacy-пайплайна** — `strategy_router.py` по-прежнему использует `base_system_prompt.py`. Переключение на новые промпты — отдельное решение.

---

## 7. Рекомендации по дальнейшей работе

1. **Интеграционный тест с реальным DeepSeek API** — прогнать 3–5 URL через `OrganizationProcessor.process()`, оценить качество классификации и cache hit rate.
2. **Подключение к Core API** — реализовать `core_client/` с реальными HTTP-вызовами (POST/PATCH) и обработкой ответов.
3. **Переключение `prompt_registry.py`** — после валидации качества заменить `get_extraction_prompt()` на роутинг к `build_organization_system_prompt()` / `build_event_system_prompt()`.
4. **Мониторинг** — вывести `DeepSeekClient.get_metrics()` в structlog / Prometheus для отслеживания cache hit rate и стоимости.
5. **Расширение few-shot примеров** — добавить пример rejected-организации (детский сад, фитнес-клуб без маркера 55+) для калибровки порога отклонения.
