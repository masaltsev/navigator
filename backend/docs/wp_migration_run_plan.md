# План запуска миграции данных из WordPress (текущий цикл)

**Дата плана:** 2026-02-17  
**Основа:** [wp_migration_step_by_step.md](wp_migration_step_by_step.md), [wp_migration_design.md](wp_migration_design.md), отчёт [2026-02-16__wp-migration-execution-report.md](reports/2026-02-16__wp-migration-execution-report.md)

---

## 1. Что учтено из прошлого запуска

### 1.1. URL из hp_site → Sources ✅

**Проблема (прошлый раз):** URL из `hp_site` сохранялись только в `organizations.site_urls`, записи в таблицу `sources` не создавались.

**Сделано сейчас:** В `WpToCoreMigrator` добавлен вызов `ensureSourcesFromSiteUrls($organization)` после привязки таксономий. Для каждого уникального базового URL (scheme + host) из `site_urls` создаётся запись в `sources` с:
- `kind` = `org_website`
- `base_url` = нормализованный URL (без пути)
- `name` = хост
- `is_active` = true, `last_status` = pending
- **`organizer_id`** = ID организатора этой организации (связь source → organizer)

Дедубликация по `base_url` (unique в БД). Связь **sources.organizer_id → organizers.id** нужна, чтобы Harvester при обходе сайта понимал, какую организацию/организатора обновлять при актуализации данных.

### 1.2. Venues — избыточное количество ✅

**Проблема (прошлый раз):** Много дубликатов venues (один и тот же адрес для одной организации создавался несколько раз при обновлении организации разными WP-листингами).

**Текущее состояние:** В `createVenue()` перед созданием выполняется проверка: есть ли уже venue с таким же `address_raw` у этой организации (через `whereHas('organizations')` + `where('address_raw', ...)`). Если есть — возвращается существующий, новый не создаётся.

### 1.3. Organizers — по одному на организацию ✅

**Текущее состояние:** В `ensureOrganizer()` используется проверка `Organizer::where(...)->exists()` по `organizable_type` и `organizable_id`. Если организатор уже есть — метод выходит без создания. Дубликаты не создаются.

### 1.4. Кодировка и устойчивость при создании Source ✅

**Проблема:** В данных WP встречается невалидный UTF-8 (например, в `hp_site` листинга 2066), из‑за чего PostgreSQL выдаёт `invalid byte sequence for encoding "UTF8"`.

**Сделано:** В `WpToCoreMigrator`:
- URL перед записью в `sources.base_url` проходят санитизацию UTF-8 (`sanitizeUtf8` / `iconv(..., 'UTF-8//IGNORE')`).
- Создание/обновление записи Source в `ensureSourcesFromSiteUrls` обёрнуто в try/catch: при ошибке на одном URL листинг не падает, проблемный URL пропускается.

При ошибке обработки листинга его `post_id` дописывается в `storage/logs/wp-migration-failed-listings.txt`; после миграции эти листинги можно переобработать через `--retry-failed` (см. шаг 5 ниже).

### 1.5. Прочее (уже исправлено ранее)

- **Префиксы таблиц WP:** запросы к WordPress используют raw SQL с явным префиксом (`$prefix.'posts'` и т.д.) в `WpListingRepository`.
- **Координаты PostGIS:** сохраняются через отдельный UPDATE после создания venue; инверсия широта/долгота из WP учтена.
- **Таксономии:** маппинг на thematic_categories (19→7, 13→8), organization_types и specialist_profiles через pivot, развод hp_listing_service по коду.

---

## 2. Предварительные условия

- [ ] В `.env` заданы переменные подключения к WordPress: `DB_WP_*` (хост, порт, база, пользователь, пароль, префикс).
- [ ] Подключение к Core (PostgreSQL) и к WordPress (MySQL) проверяется командой (команда миграции сама проверяет при старте).
- [ ] Справочники заполнены: `php artisan db:seed` уже выполнен (thematic_categories, services, organization_types, specialist_profiles, ownership_types).
- [ ] При повторном запуске: при необходимости предварительно очистить старые данные миграции: `php artisan navigator:cleanup-wp-migration-data --force`.

---

## 3. Порядок выполнения

### Шаг 1. Очистка (если нужен «чистый» повтор)

Если в Core уже есть данные прошлой миграции и нужен полный повтор:

```bash
php artisan navigator:cleanup-wp-migration-data --force
```

Удаляются: организации, venues, organizers, все pivot-связи (в т.ч. organization_thematic_categories, organization_organization_types, organization_specialist_profiles), статьи, запись источника `wordpress-legacy`.  
**Записи в `sources` с kind=org_website не удаляются** (они могут быть созданы заново при следующем запуске миграции).

### Шаг 2. Справочники

Если после очистки пересоздавали БД с нуля — заново заполнить справочники:

```bash
php artisan db:seed
```

Если БД не пересоздавалась и справочники уже заполнены — шаг пропустить.

### Шаг 3. Запуск миграции

```bash
php artisan navigator:migrate-from-wp-base --chunk-size=100
```

Рекомендуется `--chunk-size=100` для снижения пиковой нагрузки. При необходимости пропустить статьи:

```bash
php artisan navigator:migrate-from-wp-base --chunk-size=100 --skip-articles
```

### Шаг 4. Проверка результатов

- Количество организаций, venues, organizers (ожидаемо: организаций и организаторов одного порядка, venues без массовых дубликатов по одному адресу на организацию).
- Наличие записей в pivot: organization_thematic_categories, organization_organization_types, organization_specialist_profiles, organization_services.
- Количество записей в `sources` с `kind = 'org_website'` (должны появиться из hp_site).

Примеры проверки — в разделе «Проверка результатов» в [wp_migration_step_by_step.md](wp_migration_step_by_step.md).

### Шаг 5. Повторная обработка упавших листингов (после миграции)

При ошибках (например, невалидный UTF-8 в `hp_site`) ID листингов пишутся в файл `storage/logs/wp-migration-failed-listings.txt` (по одному ID на строку). После завершения миграции их можно обработать заново с текущими правилами (санитизация UTF-8, try/catch при создании Source):

```bash
# Повтор по умолчанию из storage/logs/wp-migration-failed-listings.txt
php artisan navigator:migrate-from-wp-base --retry-failed

# Или указать свой файл со списком ID
php artisan navigator:migrate-from-wp-base --retry-failed=/path/to/failed-ids.txt
```

Команда только переобрабатывает листинги из файла (подключение к WP и Core проверяется, статьи не мигрируются). Снова упавшие ID дописываются в тот же файл; при следующем запуске `--retry-failed` они войдут в выборку (дубликаты отфильтровываются).

---

## 4. Риски и откат

- **Сбой подключения к WP:** команда выведет ошибку и завершится; после устранения можно запустить снова (идемпотентность).
- **Частичное выполнение:** при ошибке на одном листинге счётчик Errors увеличивается, обработка продолжается. При необходимости — очистка через `navigator:cleanup-wp-migration-data` и повторный запуск.
- **Откат:** см. раздел «Откат» в [wp_migration_step_by_step.md](wp_migration_step_by_step.md).

---

## 5. Краткий чек-лист перед запуском

1. [ ] Подключение к WordPress настроено и доступно.
2. [ ] Справочники заполнены (после cleanup — заново seed).
3. [ ] Решено, нужна ли предварительная очистка (`cleanup-wp-migration-data`).
4. [ ] Запуск: `navigator:migrate-from-wp-base --chunk-size=100`.
5. [ ] После выполнения — проверка счётчиков и наличия `sources` с kind=org_website.

После выполнения миграции можно зафиксировать итог в отчёте (дата, счётчики, количество созданных org_website sources).
