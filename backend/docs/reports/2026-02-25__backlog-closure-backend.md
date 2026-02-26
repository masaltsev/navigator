# Закрытие бэклога Backend / Core API

> **Дата:** 2026-02-25  
> **Git commit:** 5110c01 (+ uncommitted changes)  
> **Область:** `backend/` — ImportController, миграции, модели  
> **Источник истины:** `docs/Navigator_Core_Model_and_API.md`

---

## Сводка

Закрыты все задачи из бэклога §11.2 (`docs/Harvester_v1_Development_Plan.md`). Из 12 задач (B1–B12): 9 реализованы, 1 отложена (B10 → Phase 2), 2 решены архитектурно (B9, B12).

## Закрытые задачи (Sprint 5)

### B8: Таблица `suggested_taxonomy_items`

- **Миграция:** `2026_02_25_093854_create_suggested_taxonomy_items_table.php`
- **Модель:** `App\Models\SuggestedTaxonomyItem` (UUID PK, `HasUuidPrimaryKey` trait)
- **Схема:**
  - `organization_id` (FK → organizations, cascade delete)
  - `source_reference` (nullable, indexed)
  - `dictionary_type` (string, indexed) — тип справочника (`services`, `thematic_categories`, etc.)
  - `suggested_name` — предложенный AI термин
  - `ai_reasoning` — обоснование от LLM
  - `status` (default `pending`, indexed) — для модерации
- **ImportController:** `storeSuggestedTaxonomy()` — `updateOrCreate` по `(organization_id, dictionary_type, suggested_name)`, предотвращает дубли при повторном импорте
- **Валидация:** `suggested_taxonomy.*.dictionary`, `suggested_taxonomy.*.term`, `suggested_taxonomy.*.reasoning`

### B9: Dadata при импорте (resolved by B11)

**Решение:** Harvester Python-клиент `DadataClient` обогащает venues geo-данными **до** отправки в Core API. `ImportController.resolveVenue()` принимает и сохраняет: `fias_id`, `fias_level`, `city_fias_id`, `region_iso`, `region_code`, `kladr_id`.

PHP `VenueAddressEnricher` остаётся для legacy venues из WP-миграции и artisan-команды `organizations:enrich-from-dadata`.

### B10: Staging-таблицы (deferred → Phase 2)

**Решение:** Текущая архитектура (прямой import с дедупликацией по `source_reference` → `inn`) достаточна для Sprint 5 и полного прохода ~5000 организаций. Staging-таблицы потребуются при внедрении UI модерации (diff-preview перед approve). Не блокирует текущую работу.

### B12: Консолидация Dadata (resolved)

**Решение зафиксировано:**

| Сценарий | Кто обогащает | Инструмент |
|----------|--------------|------------|
| Новый импорт из Harvester | Python `DadataClient` | Автоматически в `enrich_venues()` |
| Legacy venues из WP | PHP `VenueAddressEnricher` | `php artisan organizations:enrich-from-dadata` |
| Reverse geocoding по координатам | PHP `VenueAddressEnricher` | artisan / API |

PHP Dadata НЕ вызывается автоматически при `POST /api/internal/import/organizer`. Для новых импортов это не нужно.

## Ранее закрытые задачи (Sprint 4)

| Задача | Описание | Артефакт |
|--------|----------|----------|
| B1 | Миграция `source_reference` | `2026_02_25_092349` |
| B2 | Дедупликация организаций | `findExistingOrganization()` |
| B3 | Дедупликация событий | `Event::updateOrCreate(['organizer_id', 'source_reference'])` |
| B4 | `short_title` поле | `2026_02_25_092353` |
| B5 | VK URL → ID | `extractVkGroupId()` |
| B6 | Auth middleware | `AuthenticateInternalApi` (Sprint 2) |
| B7 | Lookup API | `GET /api/internal/organizers` |
| B11 | Venue geo-fields | `resolveVenue()` |

## Тесты

- **ImportTest:** 14 тестов, 57 assertions — все проходят
- Все существующие тесты не сломаны

## Файлы изменены

```
backend/app/Http/Controllers/Internal/ImportController.php  — storeSuggestedTaxonomy(), валидация
backend/app/Models/SuggestedTaxonomyItem.php                — новая модель
backend/database/migrations/2026_02_25_093854_*.php         — suggested_taxonomy_items
```
