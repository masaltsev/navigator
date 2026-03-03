# Ревизия кода и план действий по техническому долгу

**Дата:** 2026-02-20  
**Область:** Структура данных, API, отчёты, TODO в коде, миграции, очистка после WP  
**Источник истины:** `docs/Navigator_Core_Model_and_API.md` (без Harvester/AI Pipeline)

---

## 0. Целевая архитектура (структура данных и API)

### Соответствие документу

- **Доменная модель:** Реализованы справочники (ThematicCategory, Service, OrganizationType, SpecialistProfile, OwnershipType, CoverageLevel, EventCategory), полиморфные organizers, organizations, initiative_groups, individuals, venues (PostGIS), events/event_instances, articles, sources/parse_profiles.
- **Полиморфизм:** Morph map на короткие имена (Organization, InitiativeGroup, Individual) — миграция `2026_02_20_105753` приведена в соответствие.
- **Индексы и soft deletes:** По отчёту architecture-audit (2026-02-17) критические несоответствия устранены: vk_group_id/ok_group_id, sources/parse_profiles, soft deletes и индексы для events/venues/event_instances.
- **Расхождение с документом:** В документе в контракте AI ещё упоминается `problem_category_codes`; в коде везде используется `thematic_category_codes` — это корректно после рефакторинга словарей.

### Что не трогали (по заданию)

- Harvester и AI Pipeline — не анализировались.

---

## 1. Рекомендации из отчётов: что сделано, что нет

### 1.1. Architecture Audit (2026-02-17)

| Рекомендация | Статус |
|--------------|--------|
| Добавить vk_group_id, ok_group_id в organizations | ✅ Выполнено |
| Создать sources и parse_profiles | ✅ Выполнено |
| Soft deletes в events и venues | ✅ Выполнено |
| Индекс на start_datetime в event_instances | ✅ Выполнено |
| Индекс на region_iso в venues | ✅ Выполнено |
| Поле code в event_categories | ✅ Выполнено |
| Составной индекс (status, attendance_mode) в events | ✅ Выполнено |

**Итог:** Все пункты из отчёта отмечены как выполненные в том же отчёте (коммит 7fd5c5f).

---

### 1.2. Documentation Update (2026-02-17)

| Рекомендация | Статус |
|--------------|--------|
| Обновить Navigator_Core_Model_and_API.md (поля, индексы, API) | ✅ Выполнено (коммит 00e9469) |

**Итог:** Документ актуализирован.

---

### 1.3. API Testing Checklist Report (2026-02-16)

| Рекомендация | Статус |
|--------------|--------|
| Реализовать extractCoordinates() для PostGIS в API Resources | ❌ Не сделано — возвращается null, в коде placeholder |
| Реализовать пакетный импорт через очередь (POST /api/internal/import/batch) | ⚠️ Частично — эндпоинт есть, возвращает job_id; асинхронная обработка не реализована (TODO в ImportController) |
| Добавить автоматизированные тесты (Pest) для критических сценариев | ✅ Частично — есть Feature тесты (2026-02-18 отчёт: 27/29 пройдено) |
| Добавить события в БД для тестов фильтров событий | По ситуации (тесты есть, данные — при необходимости) |

---

### 1.4. API Testing Report 2026-02-18

| Рекомендация | Статус |
|--------------|--------|
| Реализовать извлечение координат из PostGIS в OrganizationResource/EventResource (extractCoordinates) | ❌ Не сделано |
| Добавить middleware аутентификации для /api/internal/* | ❌ Не сделано (TODO в routes/api.php) |
| Расширить тесты: обновление организаций, события с RRule, валидация событий | ⚠️ Частично |
| Кэширование справочников, OpenAPI/Swagger | Не сделано (улучшения) |

---

### 1.5. Dictionaries Refactoring Execution (2026-02-17)

| Рекомендация | Статус |
|--------------|--------|
| Обновить Navigator_Core_Model_and_API.md под новую модель | ✅ Сделано в documentation-update |
| Перед повторным прогоном WP — проверить конфиг mysql_wp и справочники | Актуально только пока используется миграция из WP |

---

### 1.6. Organizations without Thematic Category (2026-02-20)

| Рекомендация | Статус |
|--------------|--------|
| 332 организации без thematic_category; 116 «пустых» карточек — кандидаты на дообогащение или отсев | 📋 Зафиксировано, продуктовое решение не в рамках ревизии кода |

---

## 2. TODO в коде

### 2.1. ImportController.php

| Строка | TODO | Приоритет |
|--------|------|-----------|
| 94 | Check if organizer already exists by source_reference (if tracking is implemented) | Средний |
| 178 | Add unique identifier for events (e.g. source_reference or organizer_id + title hash) | Средний |
| 205 | Materialize event instances from rrule_string (background job) | Высокий |
| 237 | Dispatch batch import job to queue for async processing | Высокий |
| 298 | Use inn/ogrn or source_reference for uniqueness (Organization) | Средний |
| 327 | Use source_reference or name hash for uniqueness (InitiativeGroup) | Средний |
| 332 | Extract community_focus from data if available | Низкий |
| 333 | Extract established_date from data if available | Низкий |
| 351 | Implement Individual creation/update | Средний |
| 370–371 | Extract contact_phones/contact_emails from ai_source_trace or separate field | Средний |
| 389–390 | Extract kladr_id, region_iso from Dadata if available (venues) | Низкий |
| 482 | Unify identifier usage (code vs slug) for EventCategory | Средний |
| 490 | EventCategory uses slug, not code — need to map or update schema | Средний |

### 2.2. EventCategory.php

| Строка | TODO | Приоритет |
|--------|------|-----------|
| 18 | Decide which identifier to use consistently in AI pipeline and update ImportController | Средний |

### 2.3. routes/api.php

| Строка | TODO | Приоритет |
|--------|------|-----------|
| 16 | Add authentication middleware for internal API (e.g. auth:sanctum or API key) | Высокий (безопасность) |

### 2.4. Прочее

- `storage/framework/views/*.php` — сгенерированные view, не редактировать (упоминание list-artisan-commands не является TODO приложения).

---

## 3. docs/wp_migration_cleanup_guide.md — кратко

- **Когда выполнять:** После успешного завершения миграции из WP и проверки данных; только если повторная миграция не потребуется.
- **Шаги:**  
  1) Удалить `app/Services/WpMigration/` (WpListingRepository, WpTaxonomyMapper, WpToCoreMigrator).  
  2) Удалить `app/Console/Commands/MigrateFromWpBaseCommand.php`.  
  3) Удалить блок `mysql_wp` из `config/database.php`.  
  4) Опционально убрать `DB_WP_*` из `.env`.  
  5) Проверить отсутствие ссылок на удалённые классы и `mysql_wp` в app/config.  
  6) Очистить кэш (config, cache, route).
- **Важно:** В `OwnershipTypeSeeder` используется `DB::connection('mysql_wp')` для заполнения из WP. При выполнении очистки сидер нужно перевести на статические данные (как другие справочники) или отдельный источник.
- **Доп. команды:** CleanupWpMigrationDuplicatesCommand, CleanupWpMigrationDataCommand, ManualMigrateListings7419And4425 — в гайде не описаны; решить, оставлять ли их после очистки WP (если нет — удалить или вынести в архив).

---

## 4. Миграции: оптимизация (без обогащения и импорта из WP)

Условие: «не нужно заниматься обогащением и импортом данных из WP» — то есть backfill’ы и одноразовые данные-миграции можно считать выполненными один раз; для новых окружений (fresh install) нужно определиться, что входить в «чистую» схему, а что — нет.

### 4.1. Текущий список миграций (42 файла)

**Базовые (схема):**  
`0001_01_01_000001`–`0001_01_01_000030` (create_* таблиц), плюс миграции 2026_02_* для изменений схемы.

**Изменения схемы (оставить как есть или влить в базовые):**

| Файл | Назначение | Рекомендация |
|------|------------|--------------|
| 2026_02_18_193020_add_organizer_id_to_sources_table.php | organizer_id в sources | Оставить — часть текущей схемы |
| 2026_02_19_082809_add_fias_level_to_venues_table.php | fias_level в venues | Оставить или влить в create_venues при следующем «схемном» рефакторинге |
| 2026_02_19_091544_add_city_fias_id_to_venues_table.php | city_fias_id + первоначальный backfill | См. ниже |
| 2026_02_19_124354_add_region_code_to_venues_table.php | region_code в venues | Аналогично — оставить или влить в create_venues |
| 2026_02_20_105753_update_organizers_morph_map_to_short_names.php | Замена полных имён классов на short names в organizers | Одноразовая **данная** миграция |
| 2026_02_20_151808_allow_same_base_url_per_organizer_in_sources.php | Уникальность (organizer_id, base_url) в sources | Оставить — часть схемы |

**Чисто backfill (только данные, без новых колонок):**

- 2026_02_19_093721_backfill_city_fias_id_for_federal_cities.php  
- 2026_02_19_102227_backfill_city_fias_id_for_level6_settlements.php  
- 2026_02_19_102245_backfill_city_fias_id_for_level1_regions.php  
- 2026_02_19_124858_backfill_region_code_for_new_regions.php  
- 2026_02_19_125127_backfill_region_code_for_cities_and_settlements.php  

Они заполняют `city_fias_id` и `region_code` для уже существующих записей в venues (в т.ч. после миграции из WP и обогащения). Для **новых** установок без импорта WP и без обогащения эти backfill’ы не создают новых колонок и по сути ничего не делают (или делают пустые UPDATE). Их можно:

- **Вариант A:** Оставить как есть — история миграций сохраняется; на fresh DB они просто не меняют данных.  
- **Вариант B:** Не удалять из репозитория, но пометить в комментариях, что это «одноразовые данные для существующей БД после WP/обогащения».  
- **Вариант C (агрессивный):** Вынести в отдельный каталог типа `database/migrations/legacy_backfills` и не подключать к стандартному `migrate` для новых проектов (требует отдельного механизма запуска или явного решения «мигрировать ли legacy»).

**Рекомендация:** Не удалять backfill-миграции (чтобы не ломать уже применённые окружения), но в README или в docs явно описать: «миграции 2026_02_19_093721 … 125127 — одноразовое заполнение данных для venues после импорта/обогащения; на чистой БД не обязательны».

### 4.2. Объединение миграций (консолидация)

- **Не** объединять уже применённые миграции в прод/стейджинг — Laravel учитывает по именам; слияние приведёт к путанице с batches.
- Для **новых** проектов или при полном переходе на «одну начальную схему» можно один раз сделать:
  - одну миграцию `create_venues_table`, включающую все текущие поля (в т.ч. fias_level, city_fias_id, region_code, region_iso и т.д.);
  - одну миграцию `create_sources_table` с organizer_id и уникальным индексом (organizer_id, base_url) изначально.
- Консолидацию разумно делать в отдельной ветке и только для новых окружений; текущие 42 файла для уже работающих БД лучше не трогать.

### 4.3. Удаление

- **Не удалять** миграции, которые уже выполнялись на реальных БД.
- Удалять имеет смысл только если какая-то миграция была добавлена по ошибке и **никогда** не применялась ни на одной среде — тогда удалить файл и при необходимости поправить следующую по счёту миграцию.

### 4.4. Итог по миграциям

| Действие | Рекомендация |
|----------|--------------|
| Удалить backfill’ы | Не удалять; описать в документации как одноразовые данные |
| Объединить в одну create_venues | Только для новых установок и отдельной ветки; не менять уже применённые |
| Оставить все 42 файла | Да, для существующих окружений |
| Документировать назначение 2026_02_* | Да — добавить в docs/reports или README краткую таблицу (схема vs data-only) |

---

## 5. План действий (приоритизированный)

### Критично / высокий приоритет

1. **Аутентификация внутреннего API**  
   - Добавить middleware для `/api/internal/*` (Sanctum или API key).  
   - Убрать/закрыть TODO в `routes/api.php`.

2. **PostGIS координаты в ответах API**  
   - Реализовать извлечение lat/lng в `OrganizationResource` и `EventResource` (accessor в модели Venue или raw SELECT ST_X/ST_Y), чтобы `extractCoordinates()` возвращал реальные значения, а не null.

3. **Пакетный импорт (batch)**  
   - Либо реализовать постановку в очередь и обработку POST /api/internal/import/batch (TODO в ImportController), либо явно пометить в API, что эндпоинт синхронный/ограниченный.

4. **Материализация event_instances из rrule_string**  
   - Реализовать Job/команду по расписанию для генерации записей в event_instances из events.rrule_string (по документу — скользящее окно 90 дней).

### Средний приоритет

5. **Уникальность при импорте**  
   - Определить стратегию: source_reference, inn/ogrn, organizer_id+title hash — и реализовать проверку «организатор/событие уже существует» в ImportController (TODO строки 94, 178, 298, 327).

6. **EventCategory: code vs slug**  
   - Унифицировать использование в AI-контракте и ImportController (code или slug); обновить комментарий/TODO в EventCategory и ImportController.

7. **Individual и контакты организатора**  
   - Реализовать создание/обновление Individual (TODO 351); при наличии контракта — извлекать contact_phones/contact_emails из ai_source_trace или отдельного поля (TODO 370–371).

8. **Очистка после WP (по готовности)**  
   - По инструкции wp_migration_cleanup_guide: удалить WpMigration-сервисы, MigrateFromWpBaseCommand, mysql_wp из config; перевести OwnershipTypeSeeder на статические данные; при необходимости удалить или архивировать CleanupWpMigration* и ManualMigrateListings*.

### Низкий приоритет / улучшения

9. **Расширение тестов**  
   - Обновление организаций, события с RRule, валидация событий, аутентификация internal API.

10. **Документация миграций**  
    - В docs/reports или README добавить таблицу: какие миграции только схема, какие — одноразовый backfill для данных.

11. **Дополнительно**  
    - Кэширование справочников; OpenAPI/Swagger; community_focus/established_date, kladr_id/region_iso из Dadata при появлении контракта.

---

## 6. Краткая сводка

- **Архитектура:** Соответствует документу в части структуры данных и API; морф-карта и индексы приведены в порядок.
- **Отчёты:** Рекомендации по архитектуре и документации выполнены; из отчётов по API остаются: extractCoordinates, аутентификация internal, batch/RRule в импорте.
- **TODO в коде:** 15+ мест в ImportController, 1 в EventCategory, 1 в routes — часть закрыть по плану выше.
- **WP cleanup:** Выполнять по гайду после фиксации решения «миграция из WP больше не нужна»; обязательно поправить OwnershipTypeSeeder.
- **Миграции:** Не удалять и не объединять уже применённые; backfill’ы описать как одноразовые; консолидацию схемы рассматривать только для новых установок в отдельной ветке.

Если нужно, могу оформить отдельные тикеты/задачи под каждый пункт плана (например, в виде списка для трекера).
