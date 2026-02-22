# Пошаговая инструкция: Миграция данных из WordPress

## Шаг 1: Очистка данных миграции

Удалить все данные, созданные предыдущей миграцией:

```bash
php artisan navigator:cleanup-wp-migration-data --force
```

**Что удаляется:**
- Все организации (organizations)
- Все площадки (venues)
- Все организаторы (organizers)
- Все pivot-связи (organization_venues, organization_thematic_categories, organization_organization_types, organization_specialist_profiles, organization_services, event_event_categories)
- Статьи (articles)
- Системная запись источника (sources с base_url = 'wordpress-legacy')

**Примечание:** Используйте `--force` для автоматического подтверждения, или без флага для интерактивного подтверждения.

---

## Шаг 2: Заполнение справочников

Справочники заполняются статическими данными из [dictionaries_refactoring.md](dictionaries_refactoring.md) (новые имена Positive Aging):

```bash
# Запустить все seeders одной командой
php artisan db:seed

# Или по отдельности:
php artisan db:seed --class=ThematicCategorySeeder
php artisan db:seed --class=ServiceSeeder
php artisan db:seed --class=OrganizationTypeSeeder
php artisan db:seed --class=OwnershipTypeSeeder
php artisan db:seed --class=SpecialistProfileSeeder
```

**Что создается:**
- `thematic_categories` — жизненные ситуации (из Таблицы А; иерархия по parent_id)
- `services` — услуги (из Таблицы Б; коды 21, 22, 23 включены; 72, 81, 89, 107 исключены)
- `organization_types` — типы организаций (из Таблицы Б)
- `specialist_profiles` — профили специалистов (из Таблицы Б)
- `ownership_types` — формы собственности (OwnershipTypeSeeder при необходимости из WP)

**Важно:** Поле `code` в справочниках соответствует WP `term_id` для маппинга при миграции из WP.

**Проверка после seeders:**
```bash
php artisan tinker
\App\Models\ThematicCategory::count()
\App\Models\Service::count()
\App\Models\OrganizationType::count()
\App\Models\SpecialistProfile::count()
\App\Models\OwnershipType::count()
```

---

## Шаг 3: Запуск миграции данных

После заполнения справочников запустить миграцию:

```bash
php artisan navigator:migrate-from-wp-base --chunk-size=100
```

**Параметры:**
- `--chunk-size=100` — размер пакета обработки (по умолчанию 500)
- `--skip-articles` — пропустить миграцию статей (если нужно)

**Что мигрируется:**
- Организации (organizations) с дедубликацией по ИНН/ОГРН (типы организаций — через pivot M:N)
- Площадки (venues) с координатами (инверсия широта/долгота из WP); дедупликация по адресу в рамках одной организации
- Организаторы (organizers) — по одному на организацию (проверка через exists())
- Связи: thematic_categories, organization_types, specialist_profiles, services через соответствующие pivot-таблицы
- **Источники (sources):** для каждого уникального базового URL из hp_site создаётся запись с kind=org_website и связью organizer_id (чтобы Harvester знал, какого организатора обновлять при актуализации)
- Статьи (articles) — если не использован `--skip-articles`

**Прогресс:** Команда выводит прогресс-бар и статистику по завершении.

---

## Проверка результатов

После завершения миграции проверить:

```sql
-- Общая статистика
SELECT COUNT(*) FROM organizations;
SELECT COUNT(*) FROM venues;
SELECT COUNT(*) FROM organizers;

-- Организации с таксономиями
SELECT COUNT(DISTINCT organization_id) FROM organization_thematic_categories;
SELECT COUNT(DISTINCT organization_id) FROM organization_organization_types;
SELECT COUNT(DISTINCT organization_id) FROM organization_specialist_profiles;
SELECT COUNT(DISTINCT organization_id) FROM organization_services;
SELECT COUNT(*) FROM organizations WHERE ownership_type_id IS NOT NULL;

-- Площадки с координатами
SELECT COUNT(*) FROM venues WHERE coordinates IS NOT NULL;
```

Или через tinker:
```bash
php artisan tinker
\App\Models\Organization::has('thematicCategories')->count()
\App\Models\Organization::has('services')->count()
\App\Models\Venue::whereNotNull('coordinates')->count()
\App\Models\Source::where('kind', 'org_website')->count()
```

---

## Откат (если что-то пошло не так)

Если нужно начать заново:

```bash
# 1. Очистить данные
php artisan navigator:cleanup-wp-migration-data --force

# 2. (Опционально) Очистить справочники
php artisan tinker
# В tinker (осторожно — удалит все записи):
# \App\Models\ThematicCategory::truncate();
# \App\Models\Service::truncate();
# \App\Models\OrganizationType::truncate();
# \App\Models\SpecialistProfile::truncate();
# \App\Models\OwnershipType::truncate();

# 3. Повторить шаги 2 и 3
```

---

## Примечания

- **Идемпотентность:** Команда миграции идемпотентна — можно запускать повторно без создания дубликатов
- **Дедубликация:** Организации дедублицируются по ИНН или ОГРН
- **Координаты:** Автоматически инвертируются (WP latitude → Core longitude)
- **Справочники:** Должны быть заполнены **до** миграции данных для корректной привязки таксономий
