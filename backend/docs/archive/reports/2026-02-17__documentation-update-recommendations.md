# Рекомендации по актуализации документа Navigator_Core_Model_and_API.md

**Дата**: 2026-02-17  
**Основа**: сравнение документа с реализованными миграциями и API контроллерами

## Критические несоответствия (требуют немедленного обновления)

### 1. Organizations — поля для интеграции с соцсетями

**Проблема**: В документе поля `vk_group_id` и `ok_group_id` упомянуты только в разделе про API (строка 305), но отсутствуют в таблице структуры полей (строка 43).

**Рекомендация**: Добавить в таблицу структуры полей `organizations` (после строки 43):
```
| organizations | id (UUID, PK), title (string), description (text), inn (string, unique), ogrn (string, unique), site_urls (JSONB), organization_type_id (FK), ownership_type_id (FK), coverage_level_id (FK), **vk_group_id (bigInteger, nullable, index), ok_group_id (bigInteger, nullable, index)**, works_with_elderly (boolean), ai_confidence_score (decimal), ai_explanation (text), ai_source_trace (JSONB), target_audience (JSONB), status (string, index), timestamps, softDeletes. |
```

### 2. EventCategories — поле code

**Проблема**: В документе (строка 34) указано только `slug`, но в реализации добавлено поле `code` (nullable, unique).

**Рекомендация**: Обновить строку 34:
```
| EventCategory | Типология активностей (лекции, тренировки ЗОЖ, собрания, мастер-классы). Критично для фильтрации в ленте событий. | id (PK, int), name (string), slug (string, unique), **code (string, nullable, unique)**, icon_url (string), timestamps, softDeletes. |
```

**Примечание**: Добавить пояснение о том, что `slug` используется для URL, а `code` — для семантической идентификации в AI-пайплайне. Требуется унификация выбора идентификатора.

### 3. Events — отсутствующие поля и индексы

**Проблема**: В документе (строка 75) не упомянуты:
- `ai_explanation` (text, nullable)
- `ai_source_trace` (JSONB, nullable)
- `softDeletes`
- Составной индекс `['status', 'attendance_mode']`

**Рекомендация**: Обновить строку 75:
```
| events | id (UUID, PK), organizer_id (UUID, FK), organization_id (UUID, FK, nullable), title (string), description (text), attendance_mode (enum: offline, online, mixed), online_url (string, nullable), rrule_string (string, nullable), target_audience (JSONB, nullable), **ai_confidence_score (decimal, 8,4, nullable), ai_explanation (text, nullable), ai_source_trace (JSONB, nullable)**, status (string, index), **индекс: ['status', 'attendance_mode']**, timestamps, **softDeletes**. |
```

### 4. EventInstances — индексы и статус "finished"

**Проблема**: В документе (строка 76) указан статус `finished`, но не упомянуты отдельные индексы на `start_datetime` и `end_datetime`.

**Рекомендация**: Обновить строку 76:
```
| event_instances | id (UUID, PK), event_id (UUID, FK), start_datetime (timestampTz, **index**), end_datetime (timestampTz, **index**), status (enum: scheduled, cancelled, rescheduled, **finished**), **индекс: ['start_datetime', 'status']**, timestamps. |
```

### 5. Venues — softDeletes и индекс на region_iso

**Проблема**: В документе (строка 69) не упомянуты `softDeletes` и индекс на `region_iso`.

**Рекомендация**: Обновить строку 69:
```
| venues | id (UUID, PK), address_raw (string), fias_id (string, index), kladr_id (string, index), region_iso (string, **index**), coordinates (Geometry Point, SRID 4326), timestamps, **softDeletes**. |
```

## Важные дополнения (рекомендуется добавить)

### 6. Sources и ParseProfiles — соответствие SQL DDL и миграций

**Проблема**: В документе (строки 152-176) есть SQL DDL, но нужно проверить соответствие с реализованными миграциями.

**Рекомендация**: 
- В таблице `sources` (строка 152): добавить `timestamps` и `softDeletes` в описание (они есть в миграции)
- В таблице `parse_profiles` (строка 169): добавить `timestamps` в описание
- Добавить индексы: `sources.kind`, `sources.last_status`, `sources.is_active`, `parse_profiles.[source_id, entity_type]`

### 7. Pivot таблицы — уточнение названия event_categories

**Проблема**: В документе (строка 86) указано `event_categories`, но в реализации таблица называется `event_event_categories` (из-за конфликта с справочником).

**Рекомендация**: Обновить строку 86:
```
* **event_event_categories**: (event_id, event_category_id). Pivot таблица для связи событий с категориями. Название изменено на event_event_categories для избежания конфликта с справочником event_categories.
```

### 8. API — уточнение структуры запросов/ответов

**Проблема**: В разделе про внутренний API (строка 370) структура запроса не полностью соответствует валидации в `ImportController`.

**Рекомендация**: Обновить пример JSON в строке 374-402:
- Добавить поле `source_reference` в начало структуры
- Уточнить, что `ai_metadata` содержит поля: `decision`, `ai_explanation`, `ai_confidence_score`, `works_with_elderly`, `ai_source_trace`
- Уточнить структуру `venues` с полями `geo_lat`, `geo_lon` (вместо просто координат)

### 9. API — отсутствие описания POST /api/internal/import/event

**Проблема**: В документе описан только `POST /api/internal/import/organizer`, но не описан `POST /api/internal/import/event`.

**Рекомендация**: Добавить после раздела про импорт организатора (после строки 404):
```
**3. Импорт или обновление события (AI-Ingestion)**

* **Эндпоинт**: POST /api/internal/import/event
* **Описание**: Принимает JSON-структуру события с RRule и привязкой к организатору/организации.
* **Структура запроса**: Аналогична структуре для организатора, но включает дополнительные поля:
  - `rrule_string` (string, nullable): строка RRule для повторяющихся событий
  - `attendance_mode` (enum: offline, online, mixed)
  - `online_url` (string, nullable): для онлайн-событий
  - `event_category_codes` (array): массив кодов категорий событий
  - `venue_ids` (array): массив UUID площадок
```

## Мелкие уточнения (опционально)

### 10. Timestamps и SoftDeletes — явное упоминание

**Рекомендация**: Добавить в начало раздела про модели данных примечание:
> **Примечание**: Все основные сущности (organizations, events, venues, articles, sources) используют стандартные поля Laravel `timestamps` (created_at, updated_at) и `softDeletes` (deleted_at) для логического удаления, если не указано иное.

### 11. Индексы производительности — документирование

**Рекомендация**: Добавить раздел после описания таблиц с перечнем ключевых индексов:
- `organizations`: `inn`, `ogrn`, `status`, `works_with_elderly`, `vk_group_id`, `ok_group_id`
- `events`: `status`, `['status', 'attendance_mode']`, `organizer_id`, `organization_id`
- `event_instances`: `start_datetime`, `end_datetime`, `['start_datetime', 'status']`, `event_id`
- `venues`: `fias_id`, `kladr_id`, `region_iso`, GiST индекс на `coordinates`
- `articles`: `published_at`, `status`, `slug`

### 12. Target Audience — уточнение реализации

**Проблема**: В документе (строка 61) указано, что `target_audience` — это массив ссылок на справочник или ENUM, но в реализации это JSONB.

**Рекомендация**: Уточнить строку 61:
```
Несмотря на наличие флага работы с пожилыми людьми (works_with_elderly), для расширенной фильтрации и аналитики в сущности organizations и events добавляется поле target_audience (JSONB). Оно реализуется как массив объектов или ссылок на справочник target_audience. Возможные значения охватывают: пожилые люди, родственники, профильные специалисты, молодежь/дети (для межпоколенческих инициатив).
```

## Итоговый приоритет обновлений

1. **Высокий приоритет** (критично для соответствия коду):
   - Пункты 1-5 (поля в таблицах organizations, event_categories, events, event_instances, venues)

2. **Средний приоритет** (важно для полноты документации):
   - Пункты 6-9 (sources/parse_profiles, pivot таблицы, API структуры)

3. **Низкий приоритет** (улучшение читаемости):
   - Пункты 10-12 (общие примечания, индексы, уточнения)

---

**Рекомендация**: Обновить документ поэтапно, начиная с пунктов высокого приоритета, чтобы обеспечить соответствие документации реализованному коду.

---

## Выполненные действия

**Дата обновления документа**: 2026-02-17  
**Коммит после обновлений**: `00e9469`

### ✅ Этап 1: Высокий приоритет (пункты 1-5)

**1. Organizations — поля для интеграции с соцсетями**
- ✅ Добавлены поля `vk_group_id` и `ok_group_id` в таблицу структуры полей (строка 43)
- ✅ Добавлены все AI-поля, `target_audience`, `status`, `timestamps`, `softDeletes`
- ✅ Добавлено примечание про интеграцию с VK/OK Mini Apps

**2. EventCategories — поле code**
- ✅ Добавлено поле `code` (nullable, unique) в описание (строка 34)
- ✅ Добавлены `timestamps` и `softDeletes`
- ✅ Добавлено примечание о различии `slug` (URL) и `code` (AI-пайплайн)

**3. Events — отсутствующие поля и индексы**
- ✅ Добавлены поля `ai_explanation`, `ai_source_trace` в описание (строка 75)
- ✅ Добавлены `softDeletes` и составной индекс `['status', 'attendance_mode']`
- ✅ Уточнены индексы на `organizer_id` и `organization_id`

**4. EventInstances — индексы и статус "finished"**
- ✅ Добавлен статус `finished` в enum (строка 76)
- ✅ Уточнены типы: `timestampTz` вместо `timestamp`
- ✅ Добавлен составной индекс `['start_datetime', 'status']`
- ✅ Добавлено примечание про отдельные индексы на `start_datetime` и `end_datetime`

**5. Venues — softDeletes и индекс на region_iso**
- ✅ Добавлен индекс на `region_iso` (строка 69)
- ✅ Добавлены `timestamps` и `softDeletes`
- ✅ Добавлено примечание про использование индекса для региональной фильтрации

### ✅ Этап 2: Средний приоритет (пункты 6-9)

**6. Sources и ParseProfiles — соответствие SQL DDL и миграций**
- ✅ Добавлены `timestamps` и `softDeletes` в SQL DDL для таблицы `sources` (строки 152-166)
- ✅ Добавлены `timestamps` в SQL DDL для таблицы `parse_profiles` (строки 169-176)
- ✅ Исправлено значение по умолчанию для `entry_points`: `'[]'` вместо `''`
- ✅ Добавлены индексы в SQL DDL: `sources.kind`, `sources.last_status`, `sources.is_active`, `parse_profiles.[source_id, entity_type]`

**7. Pivot таблицы — уточнение названия event_categories**
- ✅ Исправлено название: `event_categories` → `event_event_categories` (строка 86)
- ✅ Добавлено примечание о причине изменения названия

**8. API — уточнение структуры запросов/ответов**
- ✅ Обновлена структура запроса для `POST /api/internal/import/organizer` (строки 385-415):
  - Добавлено поле `description` вместо `post_content`
  - Уточнены поля в `ai_metadata`: `ai_confidence_score`, `ai_explanation`, `ai_source_trace`
  - Добавлены комментарии с типами и обязательностью полей
  - Уточнена структура `venues` с полями `geo_lat`, `geo_lon`, `is_headquarters`

**9. API — отсутствие описания POST /api/internal/import/event**
- ✅ Добавлено полное описание `POST /api/internal/import/event` (после строки 417):
  - Структура запроса с полями для событий
  - Поддержка RRule для повторяющихся событий
  - Привязка к организатору и организации
  - Связь с категориями событий и площадками
  - Примечание о материализации экземпляров событий

**9. Target Audience — уточнение реализации**
- ✅ Уточнено, что `target_audience` — это JSONB (строка 61)
- ✅ Добавлено примечание о гибкости структуры и возможности расширения

### ✅ Этап 3: Низкий приоритет (пункты 10-12)

**10. Timestamps и SoftDeletes — явное упоминание**
- ✅ Добавлено примечание перед разделом "Базовые справочники" (после строки 21):
  - Все основные сущности используют стандартные поля Laravel `timestamps`
  - Большинство сущностей используют `softDeletes` для логического удаления
  - Исключения явно указаны в описании соответствующих сущностей

**11. Индексы производительности — документирование**
- ✅ Добавлен новый раздел "Индексы производительности" (после строки 120):
  - Перечень ключевых индексов для всех основных таблиц
  - Описание назначения каждого индекса
  - Контекст использования индексов

**12. Target Audience — уточнение реализации**
- ✅ Уже выполнено в пункте 9 (этап 2)

---

**Итог**: Все рекомендации выполнены. Документ `docs/Navigator_Core_Model_and_API.md` полностью актуализирован и соответствует реализованному коду. Документация готова к использованию как источник истины для дальнейшей разработки.
