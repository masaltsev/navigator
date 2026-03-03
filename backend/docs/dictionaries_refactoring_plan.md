# План рефакторинга справочников и повторной миграции из WordPress

**Основа:** [dictionaries_refactoring.md](./dictionaries_refactoring.md)  
**Ссылки:** [wp_migration_design.md](./wp_migration_design.md), [wp_migration_step_by_step.md](./wp_migration_step_by_step.md), отчёты в [reports/](./reports/)

---

## Цели

1. Привести справочники в соответствие с новой архитектурой (жизненные ситуации, виды услуг, типы организаций, профили специалистов).
2. Восстановить иерархию и убрать негативный нейминг.
3. Провести миграцию из WordPress с нуля с учётом прошлых ошибок и исправлений.

---

## Этап 1. Очистка БД и удаление таблиц

**Цель:** Полностью очистить БД и создать структуру с нуля. Возврат к старой БД не планируется.

**Решение:** Делаем миграцию **с нуля**. Дамп БД можно не создавать — особого смысла в возврате к старой БД не будет.

### 1.1. Команда очистки миграционных данных

- Адаптировать команду `navigator:cleanup-wp-migration-data` под новую схему: удалять данные, связанные с миграцией из WP:
  - организации, площадки, организаторы;
  - pivot: `organization_venues`, `organization_thematic_categories`, `organization_services`, `organization_specialist_profiles`, `organization_organization_types`;
  - статьи (по текущей логике — все или по маркеру wordpress-legacy);
  - запись источника `sources` (wordpress-legacy).
- Справочники будут пересозданы при `migrate:fresh` и заполнены сидерами.

### 1.2. Полный сброс БД (migrate:fresh)

- Выполнять **полный сброс**:
  - `php artisan migrate:fresh`
- После подготовки новых/исправленных миграций (этап 2) это удалит все таблицы и выполнит миграции заново.

### 1.3. Порядок действий

1. Подготовить миграции (этап 2).
2. Выполнить `php artisan migrate:fresh` (этап 3).

**Итог этапа 1:** Решение зафиксировано: миграция с нуля, без дампа; полный `migrate:fresh` после подготовки миграций.

---

## Этап 2. Миграции: новая структура справочников и связей

**Цель:** Исправить и добавить миграции так, чтобы структура БД соответствовала [dictionaries_refactoring.md](./dictionaries_refactoring.md).

### 2.1. Удаление старого и создание нового (порядок с учётом FK)

Рекомендуемый порядок миграций (с учётом зависимостей):

1. **Удалить старые pivot-таблицы**, зависящие от справочников:
   - `organization_problem_categories` (зависит от `problem_categories`).

2. **Удалить старую таблицу:**
   - `problem_categories`.

3. **Создать таблицы справочников** (порядок из инструкции):
   - `thematic_categories` — id, name, code (unique), is_active, **parent_id** (nullable, FK на self), timestamps, soft deletes.
   - `services` — уже есть; убедиться, что есть **parent_id** (nullable, FK на self). При необходимости добавить миграцию `add_parent_id_to_services` если колонки нет.
   - `organization_types` — без изменений структуры (таблица остаётся).
   - **Новая:** `specialist_profiles` — id, name, code (unique), is_active, timestamps, soft deletes.

4. **Типы организаций: несколько на организацию**
   - Заменить связь «одна организация — один тип» на «много ко многим»:
   - Удалить колонку `organization_type_id` из таблицы `organizations` (в новых миграциях не создавать или миграция по удалению).
   - Создать pivot `organization_organization_types` — organization_id (uuid), organization_type_id (FK), primary(organization_id, organization_type_id).
   - Это позволит корректно переносить термины из «Услуг» WP в типы организаций и привязывать к организации несколько типов.

5. **Новые pivot-таблицы:**
   - `organization_thematic_categories` — organization_id (uuid), thematic_category_id (FK), primary(organization_id, thematic_category_id).
   - `organization_specialist_profiles` — organization_id (uuid), specialist_profile_id (FK), primary(organization_id, specialist_profile_id).

6. **Не трогать** (оставить как есть):
   - `organization_services` — остаётся, ссылается на `services`.
   - `organization_venues`, `organizations` (без organization_type_id), `venues`, `organizers`, `articles`, остальные таблицы.

### 2.2. Вариант «всё с нуля»

Если выбран сценарий с **migrate:fresh**:

- В одной или нескольких миграциях:
  - не создавать `problem_categories`;
  - создавать `thematic_categories` (с `parent_id`);
  - создавать `organization_thematic_categories` вместо `organization_problem_categories`;
  - создавать `specialist_profiles` и `organization_specialist_profiles`;
- Таблицу `organization_problem_categories` в новых миграциях не создавать; при необходимости переименовать или заменить ссылки в коде на `organization_thematic_categories`.

### 2.3. Итог этапа 2

- Файлы миграций созданы/изменены.
- Порядок миграций проверен (нет циклических FK).
- После `migrate:fresh` (или целевого отката) структура БД соответствует документу рефакторинга.

---

## Этап 3. Создание структуры БД заново

**Цель:** Получить «чистую» БД с новой схемой.

### 3.1. Действия

1. Выполнить:
   ```bash
   php artisan migrate:fresh
   ```
2. Проверить наличие таблиц:
   - `thematic_categories`, `services`, `organization_types`, `specialist_profiles`;
   - `organization_thematic_categories`, `organization_services`, `organization_specialist_profiles`;
   - отсутствие `problem_categories` и `organization_problem_categories` (если они полностью выведены из схемы).

### 3.2. Проверка

- Убедиться, что все FK и индексы созданы.
- При необходимости добавить в документацию или в `wp_migration_step_by_step.md` актуальный список таблиц после рефакторинга.

**Итог этапа 3:** Структура БД создана заново и готова к заполнению справочников.

---

## Этап 4. Сидеры и наполнение справочников

**Цель:** Заполнить справочники данными по статическим массивам из [dictionaries_refactoring.md](./dictionaries_refactoring.md) (без чтения WP на этом шаге). Поле `code` — связь со старыми данными (WP `term_id`) для последующего импорта.

### 4.1. Переименование по документу

В [dictionaries_refactoring.md](./dictionaries_refactoring.md) в таблицах А и Б заданы не только перенос/удаление таксономий, но и **переименование**. Сидеры должны заполнять справочники **именно новыми именами** из колонок:

- **Таблица А:** колонка «Новое имя (Positive Aging)» → поле `name` в `thematic_categories` (старые имена — только в колонке «Обоснование / Старое имя» для справки).
- **Таблица Б:** колонка «Новое имя» → поле `name` в соответствующих таблицах; «Старое имя» — только для справки.

То есть в БД попадают только новые формулировки (Positive Aging, переименованные типы организаций, услуги, профили специалистов).

### 4.2. Сидеры (источник данных — массивы из документа)

1. **ThematicCategorySeeder**
   - Данные: Таблица А из dictionaries_refactoring.md.
   - **Имена:** брать из колонки «Новое имя (Positive Aging)» (переименование обязательно).
   - Логика: два прохода — сначала корни (`parent_code = null`), затем дочерние (находить родителя по `parent_code` → `id`).
   - Метод: `updateOrCreate(['code' => $item['code']], $item)`.
   - Уничтоженные коды: 19, 13 — в сидер не включать (маппинг 19→7, 13→8 будет в коде миграции из WP).
   - Перенесённые в услуги: 21, 22, 23 — в thematic_categories не добавлять.

2. **ServiceSeeder**
   - Данные: Таблица Б, блок «Целевая таблица: services»; **имена** — из колонки «Новое имя».
   - Все с `parent_id = null`.
   - Исключить мусорные коды: 72, 81, 89, 107.
   - Включить коды 21, 22, 23 (перенесённые из «проблем»).

3. **OrganizationTypeSeeder**
   - Данные: Таблица Б, блок «Целевая таблица: organization_types»; **имена** — из колонки «Новое имя».

4. **SpecialistProfileSeeder**
   - Данные: Таблица Б, блок «Целевая таблица: specialist_profiles»; **имена** — из колонки «Новое имя».

5. **OwnershipTypeSeeder / CoverageLevelSeeder и др.**
   - Оставить или скорректировать по документу; при необходимости заполнять из WP таксономий (hp_listing_ownership и т.д.) отдельной командой или сидером.

6. **Сводный сидер (TaxonomySeeder / DictionariesSeeder)**
   - Например, `TaxonomySeeder` или `DictionariesSeeder`, который вызывает: ThematicCategorySeeder, ServiceSeeder, OrganizationTypeSeeder, SpecialistProfileSeeder, при необходимости OwnershipTypeSeeder и др.

### 4.2. Экспорт таксономий из WP (для справки/проверки)

- Отдельно от сидеров можно реализовать экспорт текущих таксономий WP в файл (например, JSON/CSV) для сравнения с новыми справочниками и для отладки маппинга.
- Это не заменяет наполнение по статическим массивам из документа; сидеры опираются на документ, а не на «живой» экспорт из WP.

### 4.3. Порядок запуска

```bash
php artisan db:seed --class=TaxonomySeeder
# или по отдельности в нужном порядке
```

**Итог этапа 4:** Справочники заполнены; `code` везде соответствует заданному маппингу; иерархия в `thematic_categories` восстановлена.

---

## Этап 5. Основная миграция из WordPress

**Цель:** Перенести организации, площадки, организаторы, связи и статьи из WP в Core по [wp_migration_design.md](./wp_migration_design.md) и [wp_migration_step_by_step.md](./wp_migration_step_by_step.md), с учётом исправлений из отчётов.

### 5.1. Подготовка

1. Подключение к WP: конфиг `mysql_wp` и переменные `DB_WP_*` в `.env`.
2. Справочники уже заполнены (этап 4).
3. Проверка перед стартом: наличие записей в `thematic_categories`, `services`, `organization_types`, `specialist_profiles` (и при необходимости ownership_types, coverage_levels).

### 5.2. Исправления кода (учёт отчётов)

- **WpListingRepository**
  - Использовать raw SQL с явными префиксами таблиц (`$prefix.'posts'`, `$prefix.'postmeta'`) во всех запросах к WP, чтобы избежать ошибок с алиасами и префиксами.

- **WpToCoreMigrator**
  - Координаты: не передавать в Eloquent `create()`; после создания venue выполнять UPDATE с PostGIS (ST_SetSRID(ST_MakePoint(lng, lat), 4326)).
  - Инверсия: WP `hp_latitude` → longitude, WP `hp_longitude` → latitude.
  - Venues: перед созданием проверять существование venue с тем же `address_raw` у данной организации; при наличии — возвращать существующий (дедупликация).
  - Organizers: проверка существования через `Organizer::where('organizable_type', Organization::class)->where('organizable_id', $organization->id)->exists()`; не полагаться только на `$organization->organizer`.

- **WpTaxonomyMapper (или аналог)**
  - Маппинг в новые сущности:
    - `hp_listing_category` → `thematic_categories` по `code`.
    - При импорте: WP term_id 19 → code 7, term_id 13 → code 8 (перед поиском в thematic_categories).
    - term_id 21, 22, 23 → привязывать к `services` (коды 21, 22, 23 в таблице services), не к thematic_categories.
  - `hp_listing_service` → разносить по трём таблицам по коду:
    - если код в списке organization_types → привязка через pivot `organization_organization_types` (у организации может быть несколько типов);
    - если код в списке specialist_profiles → привязка через pivot `organization_specialist_profiles`;
    - иначе → привязка через pivot `organization_services`.
  - `hp_listing_type` → привязка к organization_types через pivot `organization_organization_types` (несколько типов на организацию).
  - `hp_listing_ownership` → ownership_types.

- **Модели и связи**
  - Organization: заменить связь `problemCategories()` на `thematicCategories()` (BelongsToMany с `organization_thematic_categories`).
  - Organization: заменить единственный `organizationType()` (BelongsTo) на `organizationTypes()` (BelongsToMany через `organization_organization_types`).
  - Добавить связь `specialistProfiles()` (BelongsToMany через `organization_specialist_profiles`).
  - Удалить или не использовать модель ProblemCategory; ввести ThematicCategory.

### 5.3. Последовательность выполнения миграции (по шагам)

1. Очистка данных миграции (если нужно повторить прогон):  
   `php artisan navigator:cleanup-wp-migration-data --force`  
   Команду адаптировать под новые таблицы (удалять связи с thematic_categories, specialist_profiles и т.д.).

2. Заполнение справочников уже выполнено на этапе 4.

3. Запуск миграции:
   ```bash
   php artisan navigator:migrate-from-wp-base --chunk-size=100
   ```

4. Проверка: счётчики организаций, venues, organizers, статей; отсутствие дубликатов venues/organizers; корректность связей с thematic_categories, services, organization_types, specialist_profiles.

### 5.4. Обработка ошибок (по отчёту)

- Валидация ИНН/ОГРН: пропуск или логирование при некорректных значениях.
- Длинные строки (varchar 255): при необходимости расширить поле или обрезать с логированием.
- Уникальные нарушения (ogrn/inn): не падать, логировать и продолжать (идемпотентность через updateOrCreate).

**Итог этапа 5:** Миграция из WP выполнена с нуля; данные в новой структуре; дубликаты venues/organizers не создаются благодаря исправлениям в коде.

---

## Этап 6. Рефакторинг API и обновление архитектурной документации

**Цель:** Привести публичное и внутреннее API, а также основные архитектурные документы в соответствие с обновлённой моделью данных.

### 6.1. Рефакторинг API

- **Публичное API (`/api/v1`):**
  - Заменить фильтры и поля, связанные с «категориями проблем», на жизненные ситуации: параметры и ответы использовать `thematic_categories` (например, `thematic_category_id[]` вместо `problem_category_id[]`, в ответах — `thematic_categories` вместо `categories`/`problem_categories`).
  - В ответах организаций: поддерживать несколько типов организаций (массив `organization_types` вместо одного `organization_type`).
  - При необходимости добавить в ответы организации связь с профилями специалистов (`specialist_profiles`).
- **Внутреннее API (`/api/internal`):**
  - ImportController и форматы импорта: приём и сохранение thematic_category_codes, service_codes, organization_type_codes (массив), specialist_profile_codes; обновить валидацию и маппинг под новые справочники и pivot-таблицы.
- **Ресурсы и контроллеры:**
  - OrganizationResource, EventResource и др.: заменить problemCategories на thematicCategories, organizationType на organizationTypes (массив), при необходимости добавить specialistProfiles.
  - OrganizationController (фильтры): фильтр по жизненным ситуациям (thematic_category_id), по типам организаций (несколько), по услугам и при необходимости по профилям специалистов.

### 6.2. Обновление архитектурного документа

- Переписать основной архитектурный документ **Navigator_Core_Model_and_API.md** (в репозитории navigator: `docs/Navigator_Core_Model_and_API.md` или полный путь `../docs/Navigator_Core_Model_and_API.md` относительно backend):
  - Справочники: заменить ProblemCategory на ThematicCategory (жизненные ситуации), добавить SpecialistProfile; описать связь организаций с несколькими типами (M:N).
  - Сущности и поля: organizations без organization_type_id, с связями organizationTypes(), thematicCategories(), services(), specialistProfiles(); обновить описания полей и таблиц.
  - Разделы API: обновить контракты эндпоинтов, названия параметров и структуры ответов под новую модель.

### 6.3. Обновление чек-листа тестирования API

- Привести в соответствие с новыми вводными файл **[API_TESTING_CHECKLIST.md](./API_TESTING_CHECKLIST.md)** (backend/docs):
  - Параметры фильтров: thematic_category_id (вместо problem_category_id), organization_type_id[] при необходимости, specialist_profile_id[] при появлении таких фильтров.
  - Ожидаемые структуры ответов: thematic_categories, organization_types (массив), specialist_profiles.
  - При необходимости добавить сценарии проверки нескольких типов организаций и новых справочников.

**Итог этапа 6:** API и документация отражают обновлённую архитектуру; чек-лист по тесту API актуален.

---

## Этап 7. Проверка и отчёт

- Прогнать выборочные проверки (количество записей, связи, иерархия thematic_categories, несколько типов организаций).
- Обновить [wp_migration_step_by_step.md](./wp_migration_step_by_step.md) под новую схему (названия таблиц и справочников).
- При необходимости обновить [wp_migration_design.md](./wp_migration_design.md) (маппинг таксономий на thematic_categories, services, organization_types, specialist_profiles).
- Кратко зафиксировать в отчёте: что сделано, известные инциденты, рекомендации (например, импорт сайтов в `sources`).

---

## Сводная последовательность (для утверждения)

| № | Этап | Действие |
|---|------|----------|
| 1 | Очистка БД | Миграция с нуля; дамп не создаём. migrate:fresh после подготовки миграций. Команда cleanup адаптирована под новые таблицы (в т.ч. organization_thematic_categories, organization_organization_types, organization_specialist_profiles). |
| 2 | Миграции | Удалить problem_categories и organization_problem_categories; убрать organization_type_id из organizations; ввести thematic_categories (с parent_id), organization_thematic_categories, specialist_profiles, organization_specialist_profiles, organization_organization_types (M:N типов организаций); проверить services.parent_id. |
| 3 | Создание БД | Выполнить migrate:fresh. |
| 4 | Сидеры | Заполнение **новыми именами** из колонок «Новое имя» таблиц А и Б документа. ThematicCategorySeeder, ServiceSeeder, OrganizationTypeSeeder, SpecialistProfileSeeder; общий TaxonomySeeder. Опционально: экспорт таксономий WP для сверки. |
| 5 | Миграция из WP | Исправить WpListingRepository, WpToCoreMigrator, маппер таксономий; маппинг 19→7, 13→8; 21,22,23 в services; привязка к thematic_categories, services, organization_types (несколько через pivot), specialist_profiles; дедупликация venues и проверка organizers. Запуск navigator:migrate-from-wp-base. |
| 6 | API и документация | Рефакторинг публичного и внутреннего API под thematic_categories, несколько organization_types, specialist_profiles. Переписать Navigator_Core_Model_and_API.md и обновить API_TESTING_CHECKLIST.md. |
| 7 | Проверка | Проверки БД и обновление wp_migration_step_by_step.md, wp_migration_design.md; отчёт. |

---

## Риски и зависимости

- Изменение имён таблиц и моделей затронет API (фильтры по категориям/жизненным ситуациям, типы организаций, профили специалистов) и внутренний импорт (ImportController). Этап 6 явно включает рефакторинг API и обновление чек-листа.
- Старые миграции: при migrate:fresh все таблицы пересоздаются; в новых миграциях не создавать problem_categories и organization_problem_categories; не создавать organization_type_id в organizations.
- Сидеры заполняют только те коды и **новые имена** из документа; отсутствующие в WP коды не помешают миграции; лишние term_id в WP маппятся по правилам (19→7, 13→8 и т.д.).

После утверждения плана можно переходить к реализации по этапам.
