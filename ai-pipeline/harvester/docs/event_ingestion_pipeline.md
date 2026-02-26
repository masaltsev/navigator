# Универсальный пайплайн приёма мероприятий (Event Ingestion Pipeline)

**Источник истины:** [docs/Navigator_Core_Model_and_API.md](../../../docs/Navigator_Core_Model_and_API.md), [aggregators_guide.md](aggregators_guide.md)  
**Связанные документы:** [harvest-flows-a-b-c.md](harvest-flows-a-b-c.md) (потоки по организациям и когда запускается сбор событий), [event-harvest-policy.md](event-harvest-policy.md) (политика: когда запускать отдельный проход по мероприятиям).

Источники сырых данных о мероприятиях в Harvester разнообразны: агрегаторы (Silver Age), страницы организаций (/news, /afisha), в будущем — соцсети (VK, Telegram). Чтобы перед отправкой в бэкенд получать **единую по структуре и качеству** карточку мероприятия, все источники сходятся в одном пайплайне. **Когда** запускать сбор мероприятий (отдельный проход или в рамках обхода) решает отдельная политика, см. [event-harvest-policy.md](event-harvest-policy.md).

---

## Идея

1. **Канонический вход** — любой источник преобразует свои данные в `RawEventInput` (адаптер).
2. **Единый пайплайн** — парсинг дат (если есть `date_text`) → классификация через DeepSeek (EventProcessor) → сборка payload для Core API.
3. **Один контракт с Core** — на выходе всегда один и тот же набор полей для `POST /api/internal/import/event`.

Триггером служит «поиск или находка мероприятия»: обнаружение кандидата на странице сайта (event_discovery), импорт из агрегатора, в будущем — пост в соцсети.

---

## Модель входа: RawEventInput

Модуль: `event_ingestion.models.RawEventInput`.

| Поле | Обязательное | Описание |
|------|--------------|----------|
| `source_reference` | да | Уникальный идентификатор (дедуп в Core). |
| `title` | да | Название мероприятия. |
| `raw_text` | да | Текст для LLM: описание, markdown страницы, пост. |
| `source_url` | да | URL страницы/поста (→ `event_page_url` и `ai_source_trace`). |
| `source_kind` | да | Тип источника: `platform_silverage`, `org_website`, `vk_group`, `tg_channel` и т.д. |
| `date_text` | нет | Человекочитаемая дата/время (парсится в ISO). |
| `start_datetime_iso` / `end_datetime_iso` | нет | Уже известные даты в ISO. |
| `location` | нет | Место проведения. |
| `is_online` | нет | Онлайн-мероприятие. |
| `registration_url` | нет | Ссылка на регистрацию. |
| `category_from_source` | нет | Категория на стороне источника. |
| `region_hint` | нет | Регион для LLM. |
| `discovered_from` | нет | Откуда пришло (base_url, id агрегатора). |

Константы `source_kind`: `event_ingestion.models.SOURCE_KIND_*`.

---

## Пайплайн: шаги

1. **Парсинг дат**  
   Если задан `date_text` и нет `start_datetime_iso`/`end_datetime_iso`, используется `utils.date_parse.parse_date_text_to_iso()` (русские фразы → ISO с таймзоной Москвы).

2. **Классификация**  
   `RawEventInput` → `HarvestInput` → `EventProcessor.process()` (DeepSeek) → `EventOutput`.  
   Оттуда берутся: категории (event_category_codes, thematic_category_codes), target_audience, ai_metadata, при необходимости описание и расписание.

3. **Сборка payload для Core**  
   `event_ingestion.core_payload.build_core_event_payload(EventOutput, organizer_id, event_page_url=raw.source_url, start_datetime, end_datetime, …)` — только поля, принимаемые `ImportController::importEvent`.

Если LLM недоступен или падает, используется fallback: дефолтная классификация и `decision: needs_review`.

---

## Адаптеры

| Источник | Адаптер | Модуль |
|----------|---------|--------|
| Страницы сайта организации (/news, /afisha) | `event_candidate_to_raw(EventCandidate, source_id)` | `event_ingestion.adapters` |
| Silver Age (silveragemap.ru) | `silverage_event_to_raw(SilverAgeEvent)` | `event_ingestion.adapters` |
| Будущие: VK, Telegram, другие агрегаторы | Свой адаптер → `RawEventInput` | — |

После адаптера вызывается `run_event_ingestion_pipeline(raw, organizer_id, ...)`.

---

## Где вызывается пайплайн

| Точка входа | Как получают organizer_id | Модуль/задача |
|-------------|---------------------------|----------------|
| Обход сайта организации (event discovery) | `get_source(source_id)` → `organizer_id` | `workers.tasks.harvest_events` → `_run_event_pipeline` |
| Агрегатор Silver Age | Платформенный организатор (get-or-create по `silverage_platform`) | `aggregators.silverage.silverage_pipeline._process_event` |
| Скрипт импорта Silver Age | То же (get-or-create в скрипте) | `scripts.import_silverage_events` |

Для событий с сайта организации обязателен `source_id`, по которому в Core можно получить `organizer_id` (источник привязан к организатору). Для агрегаторов используется один организатор на платформу.

---

## Использование в коде

```python
from event_ingestion import (
    RawEventInput,
    run_event_ingestion_pipeline,
    event_candidate_to_raw,
    silverage_event_to_raw,
)

# Для кандидата с сайта организации
raw = event_candidate_to_raw(candidate, source_id=source_id)
payload = run_event_ingestion_pipeline(raw, organizer_id)

# Для агрегатора Silver Age
raw = silverage_event_to_raw(silverage_event)
payload = run_event_ingestion_pipeline(
    raw,
    organizer_id,
    title_override=silverage_event.title,
    description_override=...,
)
await core_client.import_event(payload)
```

---

## Расширение: новый источник

1. Добавить константу `source_kind` в `event_ingestion.models` при необходимости.
2. Реализовать адаптер: **нативная структура** → `RawEventInput`.
3. В точке триггера (скрипт, воркер, стратегия) вызывать адаптер и `run_event_ingestion_pipeline(raw, organizer_id, ...)`.
4. Полученный `payload` передавать в `core_client.import_event(payload)`.

Классификация, даты и формирование payload для Core остаются общими; меняется только способ заполнения `RawEventInput`.

---

## Связанные документы

| Документ | О чём |
|----------|--------|
| [harvest-flows-a-b-c.md](harvest-flows-a-b-c.md) | Потоки обогащения организаций (А–В); место событий в общей схеме. |
| [event-harvest-policy.md](event-harvest-policy.md) | Политика: когда запускать отдельный сбор мероприятий, когда не запускать. |
| [aggregators_guide.md](aggregators_guide.md) | Агрегаторы (ФПГ, СО НКО, Silver Age); мероприятия через пайплайн. |
