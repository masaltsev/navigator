# Закрытие бэклога Python-пайплайн (Harvester)

> **Дата:** 2026-02-25  
> **Git commit:** 5110c01 (+ uncommitted changes)  
> **Область:** `ai-pipeline/harvester/` — prompts, strategies, search, tests  
> **Источник истины:** `docs/Harvester_v1_Development_Plan.md`

---

## Сводка

Закрыты все задачи из бэклога §11.1 (`docs/Harvester_v1_Development_Plan.md`). Из 11 задач (H1–H11): все Done/✅. Python-пайплайн полностью готов к полному прогону 5000 организаций.

## Закрытые задачи (Sprint 5, данная сессия)

### H6: Удаление legacy-кода

**Что удалено:**
- `prompts/prompt_registry.py` — stub registry, не использовался
- `prompts/base_system_prompt.py` — минимальный system prompt для Phase 1
- `strategies/strategy_router.py` — CSS/LLM router, заменён `OrganizationProcessor` + `MultiPageCrawler`

**Верификация:** `rg` подтвердил, что ни один активный модуль (`run_single_url.py`, `batch_test.py`, `workers/tasks.py`, `enrich_sources.py`) не импортирует эти файлы. Обновлён `prompts/__init__.py` — удалены упоминания legacy-модулей.

### H7: Интеграционный тест DeepSeek

**Файл:** `tests/test_integration_deepseek.py`

| Тест | Описание | Ожидание |
|------|----------|----------|
| `test_kcson_accepted` | КЦСОН — организация для пожилых | decision=accepted, elderly=True, conf≥0.80 |
| `test_kindergarten_rejected` | Детский сад — не для пожилых | decision=rejected, elderly=False, conf≤0.30 |
| `test_nko_accepted` | АНО «Старшее поколение» | decision=accepted, elderly=True, conf≥0.70 |
| `test_cache_hit_rate` | Cache hit rate после 3 вызовов | rate > 0 (system prompt кешируется) |
| `test_output_schema_complete` | Полный payload для Core | все обязательные поля присутствуют |

**Skip-условие:** `@pytest.mark.skipif(not DEEPSEEK_API_KEY)` — тесты не запускаются без ключа, не ломают CI.

### H10: Веб-поиск + обогащение org_website

Модуль `search/` уже полностью реализован в ходе Sprint 5 (до данной сессии):

| Файл | Описание |
|------|----------|
| `search/provider.py` | Абстрактный `WebSearchProvider` + `SearchResult` |
| `search/duckduckgo_provider.py` | DuckDuckGo provider (бесплатный, MVP) |
| `search/yandex_xml_provider.py` | Yandex Search API provider (продакшен, RU-quality) |
| `search/url_fixer.py` | Исправление битых URL: поиск + scoring + reachability |
| `search/source_discoverer.py` | Обнаружение сайтов для организаций без source |
| `search/social_classifier.py` | Классификация VK/OK/TG URL по паттернам |
| `search/site_verifier.py` | LLM-верификация: crawl + проверка identity match |
| `search/candidate_filter.py` | Фильтрация агрегаторов, дедупликация, нормализация |
| `search/enrichment_pipeline.py` | End-to-end tiered pipeline (AUTO/REVIEW/REJECT) |
| `scripts/enrich_sources.py` | CLI: 7 режимов (fix-urls, fix-scheme, check-reachable, find-missing, verified-варианты) |

**Тесты:** 6 файлов — `test_search_provider.py`, `test_social_classifier.py`, `test_url_fixer.py`, `test_url_validator.py`, `test_source_discoverer.py`, `test_yandex_xml_provider.py`.

### H11: Интеграция SiteExtractor/CSS в enrichment pipeline

Уже реализовано: `run_single_url.py` вызывает `SiteExtractorRegistry.extract_if_known()` перед LLM. Для socinfo.ru и аналогов — 0 LLM-токенов.

## Ранее закрытые задачи

| Задача | Sprint | Описание |
|--------|--------|----------|
| H1 | 3 | Multi-page стратегия (17 паттернов) |
| H2 | 3 | Title enrichment через /o-nas, /svedeniya |
| H3 | 4 | Firecrawl fallback для SPA |
| H4 | 5 | `suggested_taxonomy` в few-shot примерах |
| H5 | 5 | org_type_codes fix для НКО |
| H8 | 5 | Пример rejected-организации |
| H9 | 4 | Event harvesting |

## Итоговое состояние пайплайна

```
Pipeline:
  Crawl:     MultiPageCrawler (до 5 subpages) + Firecrawl fallback
  Classify:  OrganizationProcessor (DeepSeek, JSON mode, cache) + EventProcessor
  Enrich:    Python DadataClient (geocoding) + URL fixer + source discoverer
  Send:      NavigatorCoreClient → POST /api/internal/import/organizer
  Moderate:  suggested_taxonomy → Core suggested_taxonomy_items table

Workers:     Celery (harvest_organization, harvest_events, harvest_batch)
API:         FastAPI /harvest (async trigger, webhook callback)
CLI:         run_single_url.py, batch_test.py, enrich_sources.py

Tests:       20 test files, integration test (skip without API key)
```

## Файлы изменены

```
DELETED:  prompts/prompt_registry.py
DELETED:  prompts/base_system_prompt.py
DELETED:  strategies/strategy_router.py
MODIFIED: prompts/__init__.py — removed legacy references
CREATED:  tests/test_integration_deepseek.py — 5 integration tests
```
