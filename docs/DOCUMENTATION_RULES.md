# Правила документации и отчётов

Документ описывает, куда класть новые документы и отчёты, и как их именовать. Используется и разработчиком, и агентом (AI) при создании отчётов/спек.

**Для агента (AI):** при запросе пользователя «написать отчёт», «сохранить спецификацию» или «задокументировать» — открыть этот файл и следовать разделу **«Для AI / агента»** ниже.

---

## Для разработчика

### Где что лежит

| Тип материала | Куда класть | Примеры |
|--------------|-------------|---------|
| **Источник истины по модели и API** | `docs/` (корень репозитория) | Navigator_Core_Model_and_API.md |
| **Стратегия, планы, кросс-компонентные спеки** | `docs/` | AI_Pipeline_Navigator_Plan.md, Harvester_v1_Final Spec.md, wp_to_core_migration.md |
| **Чек-листы, пошаговые руководства, интеграции по Laravel** | `backend/docs/` | API_TESTING_CHECKLIST.md, wp_migration_step_by_step.md, address_enrichment_via_dadata.md |
| **Отчёты по тестам/аудиту/задачам бэкенда** | `backend/docs/reports/` | 2026-02-17__api-testing-report.md |
| **Спеки и отчёты по Harvester / AI-пайплайну** | `ai-pipeline/harvester/docs/` и `ai-pipeline/harvester/docs/reports/` | спеки краулера, отчёты по прогонам |
| **Легаси, справочные артефакты (не для чтения как доки)** | `docs/archive/` (или `backend/docs/reference/`) | docs/archive/wp-schema/*.json |

### Именование отчётов

- **Backend:** `backend/docs/reports/YYYY-MM-DD__краткое-имя-темы.md` (два подчёркивания между датой и темой). В начале отчёта: дата, git commit (короткий хеш), область проверки, источник истины (обычно `docs/Navigator_Core_Model_and_API.md`). Подробнее: [backend/docs/reports/README.md](../backend/docs/reports/README.md).
- **Harvester:** `ai-pipeline/harvester/docs/reports/YYYY-MM-DD__краткое-имя.md` — по той же схеме.

### Ссылки

- Внутри одного компонента — относительные пути (например, в `backend/docs/` ссылаться на `./reports/`, `./wp_migration_design.md`).
- На документ в корне — явно: `docs/Navigator_Core_Model_and_API.md` (от корня репозитория).

---

## Для AI / агента

Используй эти правила, когда пользователь просит **написать отчёт**, **сохранить спецификацию** или **задокументировать** что-то.

### Куда класть новый документ

1. **«Напиши отчёт по результатам тестов / аудита / задачи»**
   - Если темы касаются **Laravel, API, миграций, БД, бэкенда** → `backend/docs/reports/YYYY-MM-DD__краткое-имя.md`. Имя файла: дата + два подчёркивания + тема (латиница, дефисы). В начале отчёта указать: дата, commit (короткий хеш), область, источник истины `docs/Navigator_Core_Model_and_API.md`.
   - Если темы касаются **Harvester, краулера, AI-пайплайна, парсинга** → `ai-pipeline/harvester/docs/reports/YYYY-MM-DD__краткое-имя.md`. Метаданные в начале — по тому же принципу.

2. **«Сохрани спецификацию / спеку / план»**
   - Если это **общая архитектура, доменная модель, стратегия по всему проекту или по AI Pipeline в целом** → `docs/` (корень). Примеры: новая версия архитектуры, план этапа AI Pipeline, общая спеку Harvester.
   - Если это **детали реализации бэкенда** (как тестировать API, как запускать миграцию, как настроить DaData) → `backend/docs/`.
   - Если это **спека или дизайн именно Harvester** (форматы, промпты, пайпы) → `ai-pipeline/harvester/docs/`.

3. **«Обнови чек-лист / руководство»**
   - Чек-листы и пошаговые руководства по бэкенду → `backend/docs/` (например, `API_TESTING_CHECKLIST.md`).
   - Аналоги по Harvester → `ai-pipeline/harvester/docs/`.

4. **Артефакты (JSON, дампы, снимки данных)**
   - От бэкенд-команд/тестов (например, список организаций) → `backend/docs/reports/` с осмысленным именем (например, `vologda_byt_organizations.json`).
   - От Harvester (срезы результатов, дампы для отладки) → `ai-pipeline/harvester/docs/reports/` или отдельная папка `artifacts/` под docs, по договорённости.

5. **Устаревшее / легаси**
   - Не удалять без явного запроса. Переносить в `docs/archive/` (или в подпапку, например `docs/archive/wp-schema/`) и при необходимости обновить ссылки в актуальных документах.

### Именование

- Отчёты: строго `YYYY-MM-DD__topic-name.md` (латиница, дефисы, два подчёркивания).
- Спеки и планы: понятное имя без даты в имени файла, например `Harvester_v1_Final Spec.md`, `address_enrichment_via_dadata.md`.

### Ссылки при создании/редактировании

- Из `backend/docs/` на источник истины: `docs/Navigator_Core_Model_and_API.md` (от корня репозитория).
- Внутри `backend/docs/`: относительные ссылки, например `[reports/README.md](./reports/README.md)`, `[address_enrichment_via_dadata.md](./address_enrichment_via_dadata.md)`.
- Из `ai-pipeline/harvester/docs/` на общую архитектуру: `docs/Navigator_Core_Model_and_API.md` или `docs/AI_Pipeline_Navigator_Plan.md` (от корня).

---

## Краткая шпаргалка (куда положить)

| Запрос / тип | Куда |
|--------------|------|
| Отчёт по API/миграциям/тестам бэкенда | `backend/docs/reports/YYYY-MM-DD__name.md` |
| Отчёт по Harvester/AI-пайплайну | `ai-pipeline/harvester/docs/reports/YYYY-MM-DD__name.md` |
| Спека по архитектуре/модели/стратегии (вся система или AI) | `docs/` |
| Руководство/чек-лист по Laravel | `backend/docs/` |
| Спека/дизайн Harvester | `ai-pipeline/harvester/docs/` |
| Легаси-схемы, старые JSON | `docs/archive/` (или подпапка) |
