# Reports

Здесь храним **регулярные отчёты** по состоянию кода/архитектуры, чтобы было понятно:
- к какому **коммиту** относится проверка;
- на какую **дату** сделан снимок;
- какие части системы покрывались.

## Рекомендуемое именование файлов

- `YYYY-MM-DD__architecture-audit.md`
- `YYYY-MM-DD__api-audit.md`
- `YYYY-MM-DD__data-model-review.md`

## Обязательные метаданные в начале отчёта

- Дата
- Git commit (короткий хеш)
- Область (какие папки/модули проверяли)
- Источник истины (обычно `docs/Navigator_Core_Model_and_API.md`)

## Текущие отчёты

- `2026-02-16__wp-migration-execution-report.md` — выполнение миграции данных из WordPress, статистика, обнаруженные проблемы и рекомендации (commit `da432b9`)
- `2026-02-16__api-testing-report.md` — тестирование публичного и внутреннего API, исправление ошибок в трейте `HasUuidPrimaryKey` (commit `a560cd1`)
- `2026-02-17__architecture-audit.md` — первый аудит согласованности миграций, моделей и API каркаса с архитектурным документом (commit `daefe1a`)
- `2026-02-27__api-tests-description.md` — описание всех автоматических тестов API (публичный v1 и внутренний internal), по файлам и кейсам (commit `0b951e1`)

## Миграции 2026_02_* (назначение)

| Миграция | Тип | Описание |
|----------|-----|----------|
| `add_organizer_id_to_sources_table` | схема | Добавление связи источников с организатором |
| `add_fias_level_to_venues_table` | схема | Поле уровня ФИАС в venues |
| `add_city_fias_id_to_venues_table` | схема + data | Колонка city_fias_id + первичный backfill |
| `backfill_city_fias_id_for_federal_cities` | data | Backfill city_fias_id для городов фед. значения (МСК, СПб, Севастополь) |
| `backfill_city_fias_id_for_level6_settlements` | data | Backfill для населённых пунктов (level 6) |
| `backfill_city_fias_id_for_level1_regions` | data | Backfill для регионов (level 1) |
| `add_region_code_to_venues_table` | схема | Колонка region_code (ISO и т.п.) |
| `backfill_region_code_for_new_regions` | data | Заполнение region_code для регионов |
| `backfill_region_code_for_cities_and_settlements` | data | Заполнение region_code для городов и поселений |
| `update_organizers_morph_map_to_short_names` | схема/код | Morph map на короткие имена |
| `allow_same_base_url_per_organizer_in_sources` | схема | Разрешение одного base_url на организатора в sources |
