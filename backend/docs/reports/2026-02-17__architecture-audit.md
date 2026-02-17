# Отчет аудита согласованности кода с архитектурой Navigator Core

## Метаданные отчёта

- **Дата**: 2026-02-17
- **Снимок кода (git commit)**: `daefe1a`
- **Область**: миграции `database/migrations`, модели `app/Models`, публичный/внутренний API каркас
- **Источник истины**: `docs/Navigator_Core_Model_and_API.md`
- **Примечание**: репозиторий на момент генерации отчёта содержит незакоммиченные изменения (см. `git status`)

## Общие замечания

**Положительные моменты:**
- Все основные сущности из документа реализованы
- UUID первичные ключи корректно используются для всех полиморфных сущностей
- PostGIS координаты правильно настроены в `venues`
- Полиморфная архитектура `organizers` реализована корректно
- AI-поля присутствуют в нужных сущностях
- JSONB типы используются для массивов и метаданных
- Индексы на ключевых полях (status, works_with_elderly, inn, ogrn) присутствуют

**Критические несоответствия:**
1. Отсутствуют поля `vk_group_id` и `ok_group_id` в `organizations` (требуется для интеграции с VK/OK Mini Apps)
2. Отсутствует таблица `sources` для Source Manager (описана в документе как часть Harvester & Source Manager v1.1)
3. В `event_instances` отсутствует отдельный индекс на `start_datetime` (есть только составной)

**Рекомендации по улучшению:**
- Добавить soft deletes в `events` и `venues` для консистентности
- Рассмотреть добавление индекса на `start_datetime` отдельно в `event_instances`
- Добавить поля для социальных сетей в `organizations`

---

## Детальный анализ по сущностям

### 1. Organizations

#### Что не совпадает / чего не хватает:

1. **Отсутствуют поля для интеграции с социальными сетями:**
   - `vk_group_id` (integer, nullable) — ID группы ВКонтакте
   - `ok_group_id` (integer, nullable) — ID группы Одноклассников
   
   Документ явно указывает: "В целях глубокой интеграции с социальными сетями в сущности organizations и sources добавляются поля для хранения социальных идентификаторов: vk_group_id и ok_group_id."

2. **Статус как строка вместо enum:**
   - Текущая реализация: `$table->string('status')->index()`
   - Рекомендация: использовать enum для строгой типизации, но текущий подход допустим для гибкости State Machine

#### Конкретное предложение по исправлению:

**Миграция (добавить в существующую или создать новую):**

```php
// database/migrations/XXXX_XX_XX_add_social_ids_to_organizations.php
Schema::table('organizations', function (Blueprint $table) {
    $table->bigInteger('vk_group_id')->nullable()->index();
    $table->bigInteger('ok_group_id')->nullable()->index();
});
```

**Модель (добавить в casts, если нужно):**

```php
// app/Models/Organization.php
protected function casts(): array
{
    return [
        // ... существующие casts
        'vk_group_id' => 'integer',
        'ok_group_id' => 'integer',
    ];
}
```

---

### 2. Events

#### Что не совпадает / чего не хватает:

1. **Отсутствует soft deletes:**
   - Текущая реализация: нет `softDeletes()`
   - Рекомендация: добавить для консистентности с другими сущностями и возможности восстановления исторических событий

2. **Статус как строка вместо enum:**
   - Аналогично organizations, но это допустимо для State Machine

#### Конкретное предложение по исправлению:

**Миграция:**

```php
// database/migrations/XXXX_XX_XX_add_soft_deletes_to_events.php
Schema::table('events', function (Blueprint $table) {
    $table->softDeletes();
});
```

**Модель:**

```php
// app/Models/Event.php
use Illuminate\Database\Eloquent\SoftDeletes;

class Event extends Model
{
    use HasFactory, HasUuidPrimaryKey, SoftDeletes; // добавить SoftDeletes
    // ...
}
```

---

### 3. Event Instances

#### Что не совпадает / чего не хватает:

1. **Отсутствует отдельный индекс на `start_datetime`:**
   - Текущая реализация: только составной индекс `['start_datetime', 'status']`
   - Проблема: фильтрация только по `start_datetime` (без статуса) будет менее эффективной
   - Документ подчеркивает важность быстрых запросов по датам

2. **Отсутствует индекс на `event_id` отдельно:**
   - Текущая реализация: `$table->uuid('event_id')->index()` — уже есть!
   - ✅ Это правильно

#### Конкретное предложение по исправлению:

**Миграция:**

```php
// database/migrations/XXXX_XX_XX_add_start_datetime_index_to_event_instances.php
Schema::table('event_instances', function (Blueprint $table) {
    // Добавить отдельный индекс на start_datetime для фильтрации по времени
    $table->index('start_datetime');
});
```

**Обоснование:** Составной индекс `(start_datetime, status)` эффективен для запросов с обоими условиями, но отдельный индекс на `start_datetime` улучшит производительность запросов типа "все события на эту неделю" без фильтра по статусу.

---

### 4. Venues

#### Что не совпадает / чего не хватает:

1. **Отсутствует soft deletes:**
   - Текущая реализация: нет `softDeletes()`
   - Рекомендация: добавить для возможности восстановления удаленных площадок

2. **Отсутствует индекс на `region_iso`:**
   - Текущая реализация: `$table->string('region_iso')->nullable()` без индекса
   - Рекомендация: добавить индекс для фильтрации по регионам

#### Конкретное предложение по исправлению:

**Миграция:**

```php
// database/migrations/XXXX_XX_XX_add_soft_deletes_and_indexes_to_venues.php
Schema::table('venues', function (Blueprint $table) {
    $table->softDeletes();
    $table->index('region_iso');
});
```

**Модель:**

```php
// app/Models/Venue.php
use Illuminate\Database\Eloquent\SoftDeletes;

class Venue extends Model
{
    use HasFactory, HasUuidPrimaryKey, SoftDeletes; // добавить SoftDeletes
    // ...
}
```

---

### 5. Organizers

#### Что не совпадает / чего не хватает:

✅ **Все корректно:**
- Полиморфная связь настроена правильно (`uuidMorphs('organizable')`)
- JSONB для контактов корректно
- Статус индексирован
- Soft deletes присутствует

**Замечание:** Morph map зарегистрирован в `AppServiceProvider`, что правильно.

---

### 6. Initiative Groups

#### Что не совпадает / чего не хватает:

✅ **Все корректно:**
- AI-поля присутствуют
- `target_audience` как JSONB
- Статус индексирован
- Soft deletes присутствует

---

### 7. Individuals

#### Что не совпадает / чего не хватает:

✅ **Все корректно:**
- Минимальный набор полей соответствует документу
- `consent_given` присутствует
- Soft deletes присутствует

---

### 8. Articles

#### Что не совпадает / чего не хватает:

✅ **Все корректно:**
- Структура соответствует документу
- Статус как enum с правильными значениями
- Связи с `problem_categories`, `services`, `organizations` настроены
- Soft deletes присутствует

---

### 9. Event Categories (справочник)

#### Что не совпадает / чего не хватает:

1. **Использование `slug` вместо `code`:**
   - Текущая реализация: `slug` (string, unique)
   - Документ: не указывает явно, но другие справочники используют `code`
   - Проблема: в `ImportController` используется `whereIn('slug', $codes)`, что может быть несоответствием
   - Рекомендация: либо добавить поле `code` параллельно со `slug`, либо унифицировать подход

#### Конкретное предложение по исправлению:

**Вариант A (добавить code):**

```php
// database/migrations/XXXX_XX_XX_add_code_to_event_categories.php
Schema::table('event_categories', function (Blueprint $table) {
    $table->string('code')->nullable()->unique()->after('slug');
});
```

**Вариант B (использовать slug везде):**
- Обновить `ImportController::attachEventCategories()` чтобы использовать slug корректно
- Это уже реализовано, но нужно убедиться, что AI-пайплайн передает slug, а не code

---

### 10. Pivot таблицы

#### Что не совпадает / чего не хватает:

✅ **Все корректно:**
- Составные первичные ключи настроены правильно
- Foreign keys с cascade delete корректны
- Timestamps добавлены где нужно (`organization_venues`, `event_venues`)

**Замечание:** Pivot таблицы не имеют отдельных моделей, что соответствует Laravel best practices.

---

### 11. Users и Roles

#### Что не совпадает / чего не хватает:

✅ **Все корректно:**
- Минимальная RBAC реализована
- Связи `users ↔ roles` и `users ↔ organizers` настроены
- Pivot таблицы корректны

---

### 12. Sources (отсутствует)

#### Что не совпадает / чего не хватает:

1. **Отсутствует таблица `sources` для Source Manager:**
   - Документ описывает подсистему Harvester & Source Manager v1.1
   - Требуется таблица `sources` с полями:
     - `id` (UUID)
     - `name`, `kind`, `region_iso`, `fias_region_id`
     - `base_url`, `entry_points` (JSONB)
     - `parse_profile_id`, `crawl_period_days`
     - `last_crawled_at`, `last_status`, `priority`, `is_active`

2. **Отсутствует таблица `parse_profiles`:**
   - Связана с `sources`
   - Хранит стратегии обхода (`crawl_strategy`, `config` JSONB)

#### Конкретное предложение по исправлению:

**Миграция для sources:**

```php
// database/migrations/XXXX_XX_XX_create_sources_table.php
Schema::create('sources', function (Blueprint $table) {
    $table->uuid('id')->primary();
    $table->string('name');
    $table->string('kind'); // registry_sfr, registry_minsoc, org_website, vk_group, tg_channel, api_json
    $table->string('region_iso')->nullable();
    $table->uuid('fias_region_id')->nullable();
    $table->text('base_url')->unique();
    $table->jsonb('entry_points')->default('[]');
    $table->uuid('parse_profile_id')->nullable();
    $table->integer('crawl_period_days')->default(7);
    $table->timestamp('last_crawled_at')->nullable();
    $table->string('last_status')->default('pending');
    $table->integer('priority')->default(50);
    $table->boolean('is_active')->default(true);
    
    $table->timestamps();
    $table->softDeletes();
    
    $table->index('kind');
    $table->index('last_status');
    $table->index('is_active');
});
```

**Миграция для parse_profiles:**

```php
// database/migrations/XXXX_XX_XX_create_parse_profiles_table.php
Schema::create('parse_profiles', function (Blueprint $table) {
    $table->uuid('id')->primary();
    $table->uuid('source_id');
    $table->string('entity_type'); // Organization, Event
    $table->string('crawl_strategy'); // list, sitemap, api_json, rss, vk_wall
    $table->jsonb('config');
    $table->boolean('is_active')->default(true);
    
    $table->timestamps();
    
    $table->foreign('source_id')
        ->references('id')
        ->on('sources')
        ->cascadeOnDelete();
    
    $table->index(['source_id', 'entity_type']);
});
```

---

## Проверка Eloquent связей

### ✅ Правильно настроено:

1. **Organizer → organizable() (morphTo):** ✅
2. **Organization → organizer() (morphOne):** ✅
3. **InitiativeGroup → organizer() (morphOne):** ✅
4. **Individual → organizer() (morphOne):** ✅
5. **Organization → problemCategories/services/venues/events/articles:** ✅
6. **Event → organizer/organization/instances/venues/categories:** ✅
7. **Venue → organizations/events:** ✅
8. **Article → organization/problemCategory/service:** ✅
9. **User → roles/organizers:** ✅

### ⚠️ Потенциальные улучшения:

1. **EventInstance → event():**
   - ✅ Связь настроена правильно
   - Рекомендация: добавить обратную связь `hasMany` в Event (уже есть как `instances()`)

2. **Venue → events через event_venues:**
   - ✅ Связь настроена правильно
   - Замечание: Venue не имеет прямой связи с EventInstance, что правильно (связь через Event)

---

## Производительность и индексы

### ✅ Правильно настроено:

1. Индексы на `status` в основных сущностях
2. Индексы на `works_with_elderly` в organizations и initiative_groups
3. Индексы на `inn` и `ogrn` (unique)
4. GiST индекс на PostGIS координаты в venues
5. Составной индекс `(start_datetime, status)` в event_instances

### ⚠️ Рекомендации по улучшению:

1. **Event Instances:**
   - Добавить отдельный индекс на `start_datetime` (см. выше)

2. **Venues:**
   - Добавить индекс на `region_iso` для региональной фильтрации

3. **Organizations:**
   - После добавления `vk_group_id` и `ok_group_id` — индексы уже добавлены в предложении выше

4. **Events:**
   - Рассмотреть составной индекс `(status, attendance_mode)` для частых фильтров публичного API

---

## Итоговый список действий

### Критично (требуется для соответствия документу):

1. ✅ Добавить поля `vk_group_id` и `ok_group_id` в `organizations`
2. ✅ Создать таблицы `sources` и `parse_profiles` для Source Manager

### Рекомендуется (для производительности и консистентности):

3. ✅ Добавить soft deletes в `events` и `venues`
4. ✅ Добавить отдельный индекс на `start_datetime` в `event_instances`
5. ✅ Добавить индекс на `region_iso` в `venues`
6. ✅ Рассмотреть добавление `code` в `event_categories` или унифицировать использование `slug`

### Опционально (для улучшения производительности):

7. Рассмотреть составной индекс `(status, attendance_mode)` в `events`
8. Рассмотреть индекс на `published_at` в `articles` (уже есть)

---

---

## Дополнительные замечания

### Casts в моделях

✅ **Правильно настроено:**
- JSONB поля кастятся в `array` (contact_phones, contact_emails, site_urls, ai_source_trace, target_audience)
- Decimal поля используют правильную точность (`decimal:4` для ai_confidence_score)
- Boolean поля кастятся корректно
- Date/datetime поля используют правильные типы

### Типы данных

✅ **Правильно:**
- UUID для полиморфных сущностей
- JSONB для массивов и метаданных
- `timestampTz` для event_instances (timezone-aware)
- `enum` для attendance_mode и статусов event_instances
- `string` для статусов в organizations/events (гибкость State Machine)

### Потенциальные проблемы производительности

1. **Отсутствие индекса на `end_datetime` в event_instances:**
   - Может понадобиться для запросов типа "события, которые еще не закончились"
   - Рекомендация: добавить индекс, если такие запросы будут частыми

2. **Отсутствие составного индекса в events:**
   - Для публичного API часто используется фильтр `status='approved' AND attendance_mode IN (...)`
   - Рекомендация: рассмотреть индекс `(status, attendance_mode)`

---

## Заключение

Реализация в целом соответствует архитектурному документу. Основные несоответствия касаются:
1. Отсутствия полей для интеграции с социальными сетями (`vk_group_id`, `ok_group_id`)
2. Отсутствия таблиц Source Manager (`sources`, `parse_profiles`)
3. Небольших улучшений индексации для производительности

Все критические архитектурные решения (полиморфизм, UUID, PostGIS, JSONB, State Machine) реализованы корректно.

**Оценка соответствия: 85-90%**

Основная архитектура реализована правильно. Требуются доработки для полной интеграции с социальными сетями и Source Manager подсистемой.

---

## Выполненные действия

**Дата исправлений**: 2026-02-17  
**Коммит после исправлений**: `7fd5c5f`

### ✅ Шаг 1: Поля соцсетей в organizations
- Добавлены поля `vk_group_id` и `ok_group_id` в миграцию `create_organizations_table.php`
- Добавлены casts в модель `Organization`

### ✅ Шаг 2: Source Manager — таблицы sources и parse_profiles
- Создана миграция `0001_01_01_000026_create_sources_table.php`
- Создана миграция `0001_01_01_000027_create_parse_profiles_table.php`
- Созданы модели `Source` и `ParseProfile` с правильными связями и casts

### ✅ Шаг 3: Soft deletes и индексы для Events / EventInstances / Venues
- Добавлен `softDeletes()` в миграцию `create_events_table.php` и модель `Event`
- Добавлен отдельный индекс на `start_datetime` в `create_event_instances_table.php`
- Добавлен индекс на `end_datetime` в `create_event_instances_table.php`
- Добавлен `softDeletes()` и индекс на `region_iso` в миграцию `create_venues_table.php` и модель `Venue`

### ✅ Шаг 4: EventCategories — поле code
- Добавлено поле `code` в миграцию `create_event_categories_table.php`
- Добавлен комментарий в модель `EventCategory` о необходимости унификации идентификаторов
- Добавлен TODO в `ImportController` о выборе между `code` и `slug`

### ✅ Шаг 5: Дополнительные индексы для производительности
- Добавлен составной индекс `['status', 'attendance_mode']` в `create_events_table.php`
- Добавлен индекс на `end_datetime` в `create_event_instances_table.php`
- Проверено: индекс на `published_at` в `articles` уже существует

### ✅ Шаг 6: Финальный проход
- Проверены все миграции и модели на соответствие архитектуре
- Подтверждено наличие `softDeletes()` во всех моделях, использующих `SoftDeletes`
- Проверены связи и casts во всех изменённых моделях

**Итог**: Все критические несоответствия из отчёта устранены. Код готов к первому запуску миграций.
