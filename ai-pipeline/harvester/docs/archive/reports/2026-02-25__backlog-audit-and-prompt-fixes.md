# Аудит бэклога Harvester v1 + исправления промптов + H11

- **Дата:** 2026-02-25
- **Git commit:** 5110c01 (develop, + uncommitted fixes)
- **Область:** `ai-pipeline/harvester/prompts/`, `search/enrichment_pipeline.py`, `docs/Harvester_v1_Development_Plan.md`
- **Источник истины:** `docs/Harvester_v1_Development_Plan.md` §11, отчёты Sprint 1–4

---

## 1. Цель

Ревизия бэклога после завершения Sprint 4 и начала Sprint 5 (веб-поиск + обогащение источников). Определить, какие задачи закрыты, какие остаются, и внести исправления, которые можно сделать прямо сейчас.

---

## 2. Статус бэклога: Python-пайплайн (H-серия)

| # | Приоритет | Задача | Статус | Комментарий |
|---|-----------|--------|--------|-------------|
| **H1** | ~~🟡~~ | Multi-page стратегия | ✅ Sprint 3 | `strategies/multi_page.py` — 17 паттернов |
| **H2** | ~~🟡~~ | Title: LLM перефразирует название | ✅ Sprint 3 | Multi-page подтягивает /o-nas |
| **H3** | ~~🟡~~ | Firecrawl fallback | ✅ Sprint 4 | `strategies/firecrawl_strategy.py` |
| **H4** | ~~🟢~~ | `suggested_taxonomy` пустой | ✅ **Исправлено сейчас** | Добавлен Пример 5 с non-empty `suggested_taxonomy` |
| **H5** | ~~🟢~~ | `org_type_codes` пустой для НКО | ✅ **Исправлено сейчас** | Исправлена подсказка «82 — НКО» + Пример 5 с ownership="162" |
| **H6** | 🟢 | Legacy `prompt_registry.py` | ⏳ Низкий приоритет | Используется только `strategy_router` (путь `--crawl-only`). Основной пайплайн через `organization_prompt.py` |
| **H7** | 🟢 | Интеграционный тест DeepSeek | ⏳ Низкий приоритет | Будет покрыт при полном прогоне 4.6 |
| **H8** | ~~🟢~~ | Пример rejected-организации | ✅ **Исправлено сейчас** | Добавлен Пример 4 (Детский сад — rejected, confidence=0.10) |
| **H9** | ~~🟡~~ | Event harvesting | ✅ Sprint 4 | `strategies/event_discovery.py`, CLI, Celery |
| **H10** | 🔴 | Веб-поиск + обогащение | 🔄 **В работе (Sprint 5)** | `search/` модуль реализован, верификация работает |

**Итого H-серия:** 8 из 10 закрыты. H6, H7 — низкий приоритет, не блокируют. H10 — в активной работе.

---

## 3. Статус бэклога: Backend / Core API (B-серия)

| # | Приоритет | Задача | Статус | Блокирует |
|---|-----------|--------|--------|-----------|
| **B1** | 🔴 | Миграция `source_reference` | ❌ Не сделано | Полный проход 4.6 |
| **B2** | 🔴 | Дедупликация организаций | ❌ Не сделано | Полный проход 4.6 |
| **B3** | 🔴 | Дедупликация событий | ❌ Не сделано | Полный проход 4.6 |
| **B4** | 🟡 | Миграция `short_title` | ❌ Не сделано | Данные теряются |
| **B5** | 🟡 | `vk_group_url` → `vk_group_id` | ❌ Не сделано | Покрывается Sprint 5 social_classifier |
| **B6** | ~~🟡~~ | Auth middleware internal API | ✅ Sprint 2 | — |
| **B7** | 🟡 | GET organizers lookup | ❌ Не сделано | Идемпотентность |
| **B8** | 🟢 | Таблица `suggested_taxonomy_items` | ❌ Не сделано | Данные теряются |
| **B9** | 🟢 | Dadata при импорте | ❌ Не сделано | fias_id = NULL |
| **B10** | 🟢 | Staging-таблицы | ❌ Phase 2 | — |
| **B11** | 🟡 | ImportController: fias_level, city_fias_id | ❌ Не сделано | Данные теряются |
| **B12** | 🟢 | Консолидация Dadata | ❌ Зависит от B11 | — |

**Итого B-серия:** 1 из 12 закрыт. B1-B3 критически блокируют полный проход.

---

## 4. Внесённые исправления

### 4.1. H4 → Пример с `suggested_taxonomy` (Пример 5)

**Файл:** `prompts/examples.py`

Добавлен новый few-shot пример — АНО «Образ жизни» (НКО, работающая с пожилыми). Пример демонстрирует:
- **Non-empty `suggested_taxonomy`:** «Мобильные бригады помощи» — услуга, не представленная в справочнике `services`
- Все обязательные поля TaxonomySuggestion: `target_dictionary`, `proposed_name`, `proposed_description`, `importance_for_elderly`, `source_text_fragment`

**Ожидаемый эффект:** LLM получает конкретный пример, когда и как заполнять `suggested_taxonomy`. Ранее все 3 примера имели `suggested_taxonomy: []`, и LLM не использовал это поле.

### 4.2. H5 → Исправление подсказки org_type для НКО

**Файл:** `prompts/organization_prompt.py` (Правило 3)

**Было (вводило в заблуждение):**
```
а в organization_type_codes укажи ЧТО она делает (например, "82" — НКО)
```

Код "82" — это «Досуговый центр», а не «НКО». LLM получал ложный ориентир.

**Стало:**
```
а в organization_type_codes укажи ЧТО она делает (например, "142" — Добро.Центры/волонтёрство,
"82" — досуговый центр, "99" — кризисный центр).
Если ни один код из ORGANIZATION_TYPES не подходит — оставь organization_type_codes пустым,
НЕ выдумывай код «НКО» (это НЕ organization_type, а ownership_type)
```

**Пример 5** дополнительно демонстрирует корректную классификацию НКО:
- `ownership_type_code: "162"` (АНО)
- `organization_type_codes: ["142"]` (Добро.Центры)

### 4.3. H8 → Пример rejected-организации (Пример 4)

**Файл:** `prompts/examples.py`

Добавлен Пример 4 — Детский сад №15 «Солнышко»:
- `decision: "rejected"`, `ai_confidence_score: 0.10`, `works_with_elderly: false`
- Пустые classification codes (нерелевантно для платформы)
- Чёткое объяснение в `ai_explanation`: нет маркеров 55+, пенсионеров, гериатрии

**Ожидаемый эффект:** LLM получает явный пример отклонения нерелевантной организации. Ранее все примеры были `accepted`, что создавало bias к принятию.

### 4.4. H11 → SiteExtractor в enrichment pipeline

**Файл:** `search/enrichment_pipeline.py`

В `_run_full_harvest()` добавлена проверка `_try_site_extractor(url, markdown)` перед `OrganizationProcessor`:

1. `SiteExtractorRegistry.extract_if_known(url, markdown)` — определяет платформу (socinfo.ru и др.)
2. Если платформа распознана — `_build_condensed_text()` формирует сжатый текст (~1-2K символов) из извлечённых полей (название, адрес, телефоны, email, описание, VK/OK)
3. Condensed text подаётся в `OrganizationProcessor` вместо полного markdown (~30K символов)
4. Для нераспознанных платформ — fallback на полный markdown (без изменений)

**Эффект:**
- Для socinfo.ru: ~15x меньше input-токенов на LLM-вызов
- Классификация по-прежнему через LLM (не rule-based), но с гораздо меньшим входом
- Быстрее (меньше текста для обработки LLM)
- Дешевле (~28K × $0.014/M = $0.0004 экономии на вызов)

4 юнит-теста в `tests/test_socinfo_extractor.py`.

---

## 5. Тесты

```
tests/test_prompts.py — 17 tests PASSED (0.34s)
```

Все существующие тесты промптов проходят после изменений.

---

## 6. Влияние на system prompt

| Параметр | До | После |
|----------|-----|-------|
| Few-shot примеров | 3 (все accepted) | 5 (3 accepted + 1 rejected + 1 accepted с suggested_taxonomy) |
| Примеров с `suggested_taxonomy` | 0 | 1 |
| Примеров rejected | 0 | 1 |
| Примеров НКО | 0 | 1 |
| Оценочный рост system prompt | — | ~+2K chars (~500 токенов) |

Рост незначительный: system prompt кэшируется DeepSeek (prefix caching), дополнительные 500 токенов не влияют на стоимость batch-прогона (cache hit ≥ 95%).

---

## 7. Что блокирует полный проход (4.6)

### 7.1. Критические блокеры (Laravel, B1-B3)

**Без B1-B3 полный проход создаст дубли в БД:**
- `updateOrCreate(['inn' => null])` → каждый вызов = новая организация
- Событиям вообще нет ключа дедупликации

**Минимальный набор миграций:**

```php
// B1: Добавить source_reference
Schema::table('organizations', function (Blueprint $table) {
    $table->string('source_reference')->nullable()->index();
});
Schema::table('events', function (Blueprint $table) {
    $table->string('source_reference')->nullable()->index();
});

// B2: Дедупликация организаций
// ImportController::createOrUpdateOrganization():
Organization::updateOrCreate(
    ['source_reference' => $data['source_reference'] ?? null],  // primary key
    // fallback: ['inn' => $data['inn']] если source_reference пуст
    [...]
);

// B3: Дедупликация событий
Event::updateOrCreate(
    ['source_reference' => $data['source_reference']],
    [...]
);
```

### 7.2. Инфраструктурные требования

| Компонент | Статус | Действие |
|-----------|--------|----------|
| Redis | ❓ | `docker compose up -d redis` или Homebrew |
| Ключ DeepSeek | ✅ В .env | — |
| Core API URL | ❓ | Или mock mode (работает без URL) |
| Ключ Yandex Search | ✅ В .env | Для Sprint 5 enrichment |

---

## 8. Текущий фокус: Sprint 5 (веб-поиск + обогащение)

### Завершённые этапы Sprint 5:

| Этап | Статус | Файлы |
|------|--------|-------|
| 5a: Web Search module | ✅ | `search/provider.py`, `duckduckgo_provider.py`, `yandex_xml_provider.py` |
| 5a: URL Fixer | ✅ | `search/url_fixer.py`, `search/candidate_filter.py` |
| 5b: Source Discoverer | ✅ | `search/source_discoverer.py`, `search/social_classifier.py` |
| 5b: Site Verifier | ✅ | `search/site_verifier.py`, `search/enrichment_pipeline.py` |
| CLI: enrich_sources.py | ✅ | `--fix-urls`, `--fix-urls-verified`, `--find-missing-verified`, `--harvest` |

### Текущая работа:

1. **Обход битых источников** — `--fix-urls-verified` по 171 truncated URL
2. **Следующий шаг** — `--find-missing-verified` по ~2810 организаций без источников
3. Параллельно: batch UPDATE верифицированных URL в БД

---

## 9. Рекомендации по приоритетам

### Немедленно (Python-сторона, в работе)
1. ✅ H4, H5, H8 — исправления промптов (сделано в этом отчёте)
2. 🔄 H10 — завершить обход битых URL → организации без источников

### До полного прохода (Laravel-сторона)
3. 🔴 B1-B3 — миграции `source_reference` + дедупликация (минимально для 4.6)
4. 🟡 B4 — `short_title` migration (данные готовы, теряются при импорте)

### После полного прохода
5. 🟡 B5, B11 — vk_group_id, fias_level в ImportController
6. 🟡 B7 — GET lookup для идемпотентности
7. 🟢 B8 — suggested_taxonomy_items table
8. 🟢 H6, H7 — cleanup legacy pipeline, интеграционный тест
