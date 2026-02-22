# Документация проекта Navigator

Корневая папка документации: архитектура, доменная модель, кросс-компонентные спецификации.

## Содержимое

| Документ | Назначение |
|----------|------------|
| [Navigator_Core_Model_and_API.md](Navigator_Core_Model_and_API.md) | **Источник истины** — доменная модель, API, справочники |
| [AI_Pipeline_Navigator_Plan.md](AI_Pipeline_Navigator_Plan.md) | Стратегия AI Pipeline и интеграция с ядром |
| [wp_to_core_migration.md](wp_to_core_migration.md) | Общее описание перехода WordPress → Navigator Core, маппинг данных |
| [Harvester_v1_Development_Plan.md](Harvester_v1_Development_Plan.md) | План разработки Harvester (этапы, задачи) |
| [Harvester_v1_Final Spec.md](Harvester_v1_Final Spec.md) | Финальная спецификация Harvester (структура, промпты, сидеры) |
| [full_instruction_v5.md](full_instruction_v5.md) | Промпт/инструкция для заполнения карточек (формат JSON по схеме WP) |

## Документация по компонентам

- **Backend (Laravel):** [../backend/docs/](../backend/docs/) — чек-листы API, миграции WP, DaData, гео, словари. Отчёты: [../backend/docs/reports/](../backend/docs/reports/) (см. README с правилами именования).
- **AI Pipeline / Harvester:** [../ai-pipeline/harvester/docs/](../ai-pipeline/harvester/docs/) — спецификации и отчёты по сборщику.

## Архив

- [archive/wp-schema/](archive/wp-schema/) — легаси-схемы и словари WordPress/HivePress (JSON), используются только для справки при миграции.

## Правила

Подробные правила размещения документов и отчётов: [DOCUMENTATION_RULES.md](DOCUMENTATION_RULES.md).
