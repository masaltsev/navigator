# Фаза A — Контрактная совместимость ImportController с новым AI-пайплайном

- **Дата:** 2026-02-24
- **Git commit:** 6ebf519 (uncommitted changes on top)
- **Область:** `backend/app/Http/Controllers/Internal/ImportController.php`
- **Источник истины:** `ai-pipeline/harvester/docs/reports/2026-02-24__entity-lifecycle-review.md` (пробелы G1–G8)

---

## 1. Контекст

По итогам архитектурного аудита (entity-lifecycle-review) было выявлено, что `ImportController` не принимает payload от нового AI-пайплайна (`OrganizationProcessor`). Тест Sprint 1.10 подтвердил: payload из DeepSeek API содержит поля и значения, которые валидация ImportController отклоняет.

Цель Фазы A — **минимальные правки** в одном файле для контрактной совместимости, без рефакторинга архитектуры и без новых миграций.

---

## 2. Выполненные изменения

### 2.1. G5 — `needs_review` в валидации и статусной машине

**Проблема:** AI-пайплайн возвращает `decision: "needs_review"` для неоднозначных случаев, но ImportController принимал только `accepted` и `rejected`.

**Решение:**

Валидация (строка 65):
```
'ai_metadata.decision' => 'required|string|in:accepted,rejected,needs_review'
```

`determineStatus()` — добавлена ветка:
```php
if ($decision === 'needs_review') {
    return 'pending_review';
}
```

**Верификация:** все 5 вариантов decision/confidence/elderly проверены:

| decision | confidence | elderly | → status |
|----------|-----------|---------|----------|
| accepted | 0.93 | true | approved (Smart Publish) |
| accepted | 0.70 | true | pending_review |
| accepted | 0.93 | false | pending_review |
| needs_review | 0.72 | true | pending_review |
| rejected | 0.45 | false | rejected |

### 2.2. G6 — `geo_lat`/`geo_lon` nullable

**Проблема:** Harvester не извлекает координаты (это задача Dadata). Валидация требовала `required|numeric`.

**Решение:**
```
'venues.*.geo_lat' => 'nullable|numeric'
'venues.*.geo_lon' => 'nullable|numeric'
```

Код `processVenues()` уже корректно проверяет `isset()` перед записью координат — изменения не потребовались.

Добавлено поле `venues.*.address_comment` (`nullable|string|max:500`) — передаётся из AI-пайплайна для уточнения адреса.

### 2.3. G8 — Приём `contacts` в payload

**Проблема:** `contact_phones` и `contact_emails` в `Organizer` записывались как null (TODO в коде).

**Решение:**

Валидация:
```
'contacts' => 'nullable|array'
'contacts.phones' => 'nullable|array'
'contacts.phones.*' => 'string'
'contacts.emails' => 'nullable|array'
'contacts.emails.*' => 'string|email'
```

Метод `createOrUpdateOrganizer()` — принимает `$data` и сохраняет контакты:
```php
'contact_phones' => !empty($contacts['phones']) ? $contacts['phones'] : null,
'contact_emails' => !empty($contacts['emails']) ? $contacts['emails'] : null,
```

### 2.4. Новые поля из AI-пайплайна

Добавлена валидация (все nullable, обратно совместимы):

| Поле | Валидация | Сохраняется в БД? |
|------|-----------|-------------------|
| `short_title` | `nullable\|string\|max:100` | Нет (нет колонки, Phase B) |
| `target_audience` | `nullable\|string\|max:1000` | Да → `organizations.target_audience` (array cast) |
| `site_urls` | `nullable\|array` | Да → `organizations.site_urls` (array cast) |
| `vk_group_url` | `nullable\|string\|max:255` | Нет (в БД `vk_group_id` — integer, формат отличается) |
| `ok_group_url` | `nullable\|string\|max:255` | Нет (аналогично) |
| `telegram_url` | `nullable\|string\|max:255` | Нет (нет колонки) |
| `suggested_taxonomy` | `nullable\|array` | Нет (нет таблицы, Phase B) |

### 2.5. Исправление дедупликации venues

**Проблема:** `Venue::firstOrCreate` использовал `fias_id` как ключ. При `fias_id = null` (Harvester не передаёт FIAS) каждый импорт создавал дубликат площадки.

**Решение:** fallback на `address_raw` как ключ:
```php
$matchKey = !empty($venueData['fias_id'])
    ? ['fias_id' => $venueData['fias_id']]
    : ['address_raw' => $venueData['address_raw']];
```

---

## 3. Обратная совместимость

Проверена валидация трёх payload-форматов:

| Формат | Результат |
|--------|-----------|
| Новый payload (contacts, venues без координат, needs_review) | **PASS** |
| `needs_review` decision | **PASS** |
| Старый payload (geo_lat/geo_lon, accepted/rejected, без contacts) | **PASS** |

Все новые поля — `nullable`, поэтому старые клиенты продолжают работать без изменений.

---

## 4. Что НЕ входило в Фазу A (остаётся на Phase B)

| # | Задача | Причина |
|---|--------|---------|
| G1 | Дедупликация организаций без ИНН | Нужна колонка `source_reference` (миграция) |
| G2 | Дедупликация событий | Нужна колонка `source_reference` (миграция) |
| G3 | `source_reference` как связь Source → Entity | Миграция + индекс |
| G9 | Auth middleware на internal API | Отдельная задача безопасности |
| — | Сохранение `short_title`, `vk_group_url`, `telegram_url` | Нужны новые колонки (миграция) |
| — | Сохранение `suggested_taxonomy` | Нужна отдельная таблица для модерации |

---

## 5. Рекомендации

### Sprint 2 — немедленно

1. **Миграция для `short_title`** — добавить колонку `short_title` (varchar(100), nullable) в `organizations`. Поле уже приходит из AI-пайплайна и полезно для карточек.

2. **Конвертация `vk_group_url` → `vk_group_id`** — при приёме payload парсить URL VK-группы, извлекать числовой ID и сохранять в существующую колонку `vk_group_id`. Аналогично `ok_group_id`.

3. **Тест E2E** — теперь можно отправить реальный payload от `OrganizationProcessor` в `POST /api/internal/import/organizer` и проверить полный цикл записи в БД (staging).

### Phase B — до batch-прогона (Sprint 4)

4. **Миграция `source_reference`** — добавить в `organizations`, `events`; использовать как ключ дедупликации (G1, G2, G3).

5. **Таблица `suggested_taxonomy_items`** — для накопления предложений по расширению таксономии от AI-пайплайна.

6. **Auth middleware** — `Route::middleware('auth:sanctum')` или bearer token для internal API (G9).
