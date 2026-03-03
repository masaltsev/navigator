# План очистки репозитория и подготовки миграций к первому деплою

- **Дата:** 2026-03-03
- **Commit:** 38a0c9f (develop)
- **Область:** release/v1.0, backend, harvester, миграции
- **Источник:** docs/Navigator_Core_Model_and_API.md, «Подготовка к первому деплою Navigator» (пункты 1–2)

---

## Выполнено (release/v1.0)

1. **Дамп БД** — `backend/database/dumps/navigator_prod_dump_20260303.dump` (3.2 MB, с данными)
2. **Отчёты** — перенесены в `docs/archive/reports/`, `backend/docs/archive/reports/`, `harvester/docs/archive/reports/`
3. **Удалены 8 Artisan-команд:** BackfillOrgWebsiteSources*, BackfillSourceLastCrawled*, TestCityFiasFilterApi, CheckOrganizationVenueMismatches, DatabaseConsistencyReport, DeleteSilverageEvents, RemoveDuplicateOntologyTerms, CleanupDuplicateOrganizers
4. **Harvester .gitignore:** добавлены `tests/fixtures/batch_raw/`, `data/runs/`; `git rm --cached` для уже закоммиченных
5. **Миграции:** `php artisan schema:dump --prune` — создан `database/schema/pgsql-schema.sql`, удалены 48 PHP-миграций
6. **Тесты backend:** 77 passed

---

## Влияние на develop

- Удаление отчётов/команд — только файлы, приложение работает
- batch_raw, data/runs — остаются локально, перестают коммититься
- schema:dump --prune — в локальной БД миграции уже в `migrations`; новые миграции добавляются в пустую папку `migrations/`

---

## Стратегия после мержа в main

1. `git checkout develop && git merge main`
2. Временные вещи — в .gitignore или не коммитить
3. Следующий релиз: `release/v1.1` от develop → очистка → `schema:dump --prune` → merge main → merge main в develop

---

## Связанные документы

- [BRANCH_AND_RELEASE_STRATEGY.md](../BRANCH_AND_RELEASE_STRATEGY.md)
- [wp_migration_cleanup_guide.md](../wp_migration_cleanup_guide.md)
