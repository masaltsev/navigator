# Команды: подозрительные организации и мердж дублей

Документ про команды вокруг выявления подозрительных организаций, генерации отчёта `suspicious-orgs.json` и слияния дублей в «каноническую» запись.

## Термины

- **каноническая организация**: запись `organizations`, у которой есть хотя бы одно из полей **ИНН** или **ОГРН** (не пустая строка).
- **дубликат**: запись `organizations` без ИНН и ОГРН, которую нужно влить в каноническую.
- **soft-delete**: запись помечается `deleted_at`, физически не удаляется.

## Отчёт `suspicious-orgs.json`

Команда-источник отчёта:

- **`db:report-suspicious-organizations`** (`App\Console\Commands\ReportSuspiciousOrganizationsCommand`)
  - **Зачем**: найти подозрительные названия и кандидатные дубли по названию.
  - **Что выводит**:
    - `suspicious_titles`: одобренные организации с «подозрительными» `title` (латиница, тестовые слова и т.п.).
    - `exact_title_duplicates`: группы организаций с одинаковым *нормализованным* названием, где часть без реквизитов, часть с реквизитами.
    - `fuzzy_duplicate_pairs`: пары с похожими названиями (`similar_text` ≥ порога), где одна сторона без реквизитов, вторая с реквизитами.
  - **Опции**:
    - `--similar-pct=93`: порог похожести для fuzzy-пар.
    - `--require-prefix=0`: если > 0, fuzzy-пары должны иметь одинаковый префикс из N символов после нормализации.
    - `--json`: печатать секции как JSON-объекты (удобно сохранять в файл).

Пример сохранения в файл:

```bash
cd backend
php artisan db:report-suspicious-organizations --json > suspicious-orgs.json
```

> Важно: файл `backend/suspicious-orgs.json` в проекте исторически может быть «смешанным» (текстовые строки + JSON в конце). Команды мерджа ниже умеют его парсить в текущем формате.

## Мердж дублей организаций (сервис)

Вся фактическая логика мерджа сосредоточена в:

- **`App\Services\Import\OrganizationDuplicateMergeService`**
  - **Что делает** при `mergeDuplicateIntoCanonical($canonical, $duplicate)`:
    - переносит «ценные» scalar-поля в канон, если в каноне пусто;
    - объединяет pivot-справочники (типы, категории, профили, услуги, площадки);
    - перевешивает FK зависимых сущностей (events/articles/suggested taxonomy);
    - переносит источники (`sources`) и привязки пользователей (`user_organizer`) между организаторами;
    - soft-delete дубликата и его `organizer`.

## Команды мерджа

### 1) Мердж «явных дублей» по источникам/плейсхолдерам

- **`db:merge-org-duplicates`** (`App\Console\Commands\MergeOrganizationDuplicatesCommand`)
  - **Зачем**: системно сливать дубли, которые получились из краулинга/источников.
  - **Режимы**:
    - `--dry-run`: показать план.
    - `--force`: выполнить.
  - **Что делает**:
    - ищет организации без реквизитов, но с `source_reference`, который указывает на источники, привязанные к канонической организации с реквизитами;
    - ищет «unknown title» записи (типа «Не удалось определить…») и мержит их в канон по источнику;
    - удаляет сиротские unknown-организации без связей.
  - **Дополнительно**:
    - `--report`: отчёт о расхождениях `source_reference` и фактических источников организатора.

Пример:

```bash
cd backend
php artisan db:merge-org-duplicates --dry-run
php artisan db:merge-org-duplicates --force
```

### 2) Мердж по отчёту: fuzzy title pairs

- **`db:merge-fuzzy-org-pairs`** (`App\Console\Commands\MergeFuzzyDuplicateOrganizationsCommand`)
  - **Зачем**: выполнить мердж только тех fuzzy-пар, которые прошли фильтры (медучреждения с разными номерами/регионами и очевидно разные бренды исключаются).
  - **Источник данных**: секция `fuzzy_duplicate_pairs` из `suspicious-orgs.json`.
  - **Опции**:
    - `--path=`: путь к файлу отчёта (по умолчанию `base_path('suspicious-orgs.json')`).
    - `--dry-run`, `--force`.
  - **Защиты**:
    - канон должен иметь ИНН/ОГРН;
    - дубликат не должен иметь ИНН/ОГРН;
    - обе записи должны быть не удалены.

Пример:

```bash
cd backend
php artisan db:merge-fuzzy-org-pairs --dry-run
php artisan db:merge-fuzzy-org-pairs --force
```

### 3) Мердж по отчёту: exact normalized title groups

- **`db:merge-exact-title-org-duplicates`** (`App\Console\Commands\MergeExactTitleDuplicateOrganizationsCommand`)
  - **Зачем**: мерджить «простые» группы из `exact_title_duplicates`, где:
    - есть **ровно одна** организация с ИНН/ОГРН (канон),
    - и ≥ 1 организация без реквизитов (дубли).
  - **Источник данных**: секция `exact_title_duplicates` из `suspicious-orgs.json`.
  - **Опции**:
    - `--path=`, `--dry-run`, `--force`.
  - **Защиты**: те же, что у `db:merge-fuzzy-org-pairs`.

Пример:

```bash
cd backend
php artisan db:merge-exact-title-org-duplicates --dry-run
php artisan db:merge-exact-title-org-duplicates --force
```

## Чистка тестовых артефактов в продакшене

- **`db:cleanup-test-records`** (`App\Console\Commands\CleanupProductionTestRecordsCommand`)
  - **Зачем**: удалить очевидные тестовые/фикстурные записи, которые случайно попали в продакшен.
  - **Что чистит**:
    - `sources` с `base_url`, похожими на example.com/фикстурные паттерны;
    - связанные `parse_profiles`, `organizations`, `organizers`;
    - сиротские тестовые `venues` (например адреса с «Тестовая») без привязки к живым организациям.
  - **Опции**:
    - `--dry-run`: только показать, что будет удалено;
    - `--force`: выполнить.

Пример:

```bash
cd backend
php artisan db:cleanup-test-records --dry-run
php artisan db:cleanup-test-records --force
```

## Рекомендуемый порядок работы

1. Сгенерировать свежий `suspicious-orgs.json`:
   - `php artisan db:report-suspicious-organizations --json > suspicious-orgs.json`
2. Быстрые/детерминированные мерджи по источникам:
   - `php artisan db:merge-org-duplicates --dry-run`, затем `--force`
3. Мердж exact-title групп (самый безопасный из «title-based»):
   - `php artisan db:merge-exact-title-org-duplicates --dry-run`, затем `--force`
4. Мердж fuzzy-пар (после ревью/фильтрации):
   - `php artisan db:merge-fuzzy-org-pairs --dry-run`, затем `--force`
5. Если замечены тестовые следы в проде:
   - `php artisan db:cleanup-test-records --dry-run`, затем `--force`

