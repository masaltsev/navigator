# Ревью: Жизненный цикл сущностей (Organization / Event) — от источника до БД

- **Дата:** 2026-02-24
- **Git commit:** 6ebf519 (uncommitted changes on top)
- **Область:** Backend `ImportController`, Models, Dadata, Harvester pipeline
- **Источник истины:** `docs/Navigator_Core_Model_and_API.md`, `docs/Harvester_Prompts_Spec.md`

---

## 1. Текущий бизнес-процесс: сквозная схема

```
┌─────────────────────────────────────────────────────────────────────────┐
│  ИСТОЧНИК (Source)                                                      │
│  Таблица sources: kind, base_url, organizer_id, crawl_period_days      │
│  Типы: org_website | registry_sfr | registry_minsoc | vk_group | ...   │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │
                    ┌───────────▼────────────┐
                    │  СБОР ДАННЫХ           │
                    │  Crawl4AI / Firecrawl  │
                    │  → raw HTML/Markdown   │
                    └───────────┬────────────┘
                                │
              ┌─────────────────▼──────────────────┐
              │  СТРАТЕГИЯ ИЗВЛЕЧЕНИЯ               │
              │  strategy_router.py                 │
              │  CSS-шаблон (0 токенов)             │
              │    │ fallback ↓                     │
              │  LLM Extraction (DeepSeek)          │
              │    + regex_strategy (контакты)       │
              └─────────────────┬──────────────────┘
                                │
              ┌─────────────────▼──────────────────┐
              │  КЛАССИФИКАЦИЯ (новый модуль)       │
              │  OrganizationProcessor /            │
              │  EventProcessor                     │
              │  → OrganizationOutput / EventOutput │
              │  → decision: accepted/rejected/     │
              │    needs_review                     │
              └─────────────────┬──────────────────┘
                                │
                     ┌──────────▼──────────┐
                     │  PAYLOAD BUILDER    │
                     │  to_core_import_    │
                     │  payload()          │
                     └──────────┬──────────┘
                                │
                   ┌────────────▼───────────────┐
                   │  NAVIGATOR CORE API        │
                   │  POST /api/internal/       │
                   │    import/organizer         │
                   │  POST /api/internal/       │
                   │    import/event             │
                   └────────────┬───────────────┘
                                │
              ┌─────────────────▼──────────────────┐
              │  ImportController (Laravel)         │
              │  → determineStatus()               │
              │  → createOrUpdateOrganization()    │
              │  → createOrUpdateOrganizer()        │
              │  → processVenues()                 │
              │  → attachClassifications()          │
              └─────────────────┬──────────────────┘
                                │
                   ┌────────────▼───────────────┐
                   │  БД: organizations,        │
                   │  organizers, venues,        │
                   │  pivot-таблицы              │
                   └────────────┬───────────────┘
                                │
              ┌─────────────────▼──────────────────┐
              │  ОБОГАЩЕНИЕ (POST-IMPORT)           │
              │  venues:enrich-addresses            │
              │  organizations:enrich-from-dadata   │
              │  (Artisan-команды, ручной запуск)   │
              └────────────────────────────────────┘
```

---

## 2. Идемпотентность и сопоставление с ID в БД

### 2.1. Текущее состояние: КРИТИЧЕСКИЙ ПРОБЕЛ

**Организации (`ImportController::createOrUpdateOrganization`):**

```php
// backend/app/Http/Controllers/Internal/ImportController.php:296-298
return Organization::updateOrCreate(
    ['inn' => $data['inn'] ?? null],   // ← ключ дедупликации
    [ ... ]
);
```

| Вопрос | Ответ |
|--------|-------|
| По какому полю ищется существующая запись? | `inn` (ИНН) |
| Что если ИНН = null? | `updateOrCreate(['inn' => null], ...)` — **КАЖДЫЙ вызов создаёт новую запись**. Организации без ИНН дублируются бесконтрольно |
| Используется ли `source_reference`? | **Нет.** TODO на строке 94, не реализовано |
| Используется ли `existing_entity_id`? | **Нет.** Python-пайплайн его вычисляет, но Core API его не принимает и не использует |
| Есть ли GET-эндпоинт для lookup? | **Нет.** Спецификация описывает `GET /api/internal/organizers?source_id=X&source_item_id=Y`, но он не реализован |

**События (`ImportController::importEvent`):**

```php
// backend/app/Http/Controllers/Internal/ImportController.php:176-178
$event = Event::updateOrCreate(
    [
        // TODO: Add unique identifier
    ],
    [ ... ]
);
```

Пустой массив в первом аргументе `updateOrCreate` → **каждый импорт создаёт новое событие**. Дедупликация отсутствует полностью.

**InitiativeGroup:** аналогично — TODO на строке 327.

### 2.2. Связь Source → Organizer

В модели `Source` есть поле `organizer_id` (добавлено миграцией `2026_02_18`), позволяющее связать источник с организатором. Однако:

- При импорте через API эта связь **не устанавливается**
- `source_reference` передаётся, но **не сохраняется** ни в одну таблицу
- Таблица `sources` не имеет поля `source_item_id` для отслеживания конкретных записей внутри источника

### 2.3. Что предлагает спецификация (не реализовано)

Спецификация (`Harvester_Prompts_Spec.md`, раздел 2.12) описывает двухуровневую идемпотентность:

1. **Технический ключ**: `(source_id, source_item_id)` — уникальный составной индекс
2. **Бизнес-ключ**: ИНН/ОГРН + название — для кросс-источниковой дедупликации

Ни один из уровней не реализован на стороне Core API.

---

## 3. Dadata: текущая роль в пайплайне

### 3.1. Реализованная функциональность (Backend, PHP)

| Компонент | Файл | Что делает |
|-----------|------|------------|
| `DadataClient` | `app/Services/Dadata/DadataClient.php` | suggestAddress, cleanAddress, reverseGeocode, findPartyById |
| `VenueAddressEnricher` | `app/Services/VenueAddressEnricher/` | Обогащает venue: fias_id, kladr_id, region_iso, coordinates |
| `venues:enrich-addresses` | Artisan-команда | Батч-обогащение адресов площадок через Dadata |
| `organizations:enrich-from-dadata` | Artisan-команда | Обогащение орг-ций через findPartyById (ИНН/ОГРН): дозаполнение ИНН/ОГРН, контакты, адреса |

### 3.2. ВАЖНО: Dadata работает ОТДЕЛЬНО от пайплайна импорта

```
Импорт (ImportController)              Dadata-обогащение
────────────────────────                ──────────────────
POST /import/organizer                  artisan venues:enrich-addresses
  → Organization.updateOrCreate         artisan organizations:enrich-from-dadata
  → Venue.firstOrCreate                   → DadataClient.suggestAddress
  → БД запись создана                     → VenueAddressEnricher.enrichByAddress
                                          → venue.fias_id = ...
  Dadata НЕ вызывается!                  → venue.coordinates = ...
  fias_id остаётся NULL                   → venue.save()
  coordinates = переданные из payload
  (если не переданы → NULL)             Запускается вручную. Отдельный процесс.
```

**Ключевые наблюдения:**

1. **Dadata НЕ интегрирована в процесс импорта.** `ImportController` принимает `geo_lat`/`geo_lon` и `fias_id` из payload, но если Harvester их не предоставляет (а он не предоставляет — в `OrganizationOutput.venues` есть только `address_raw` и `address_comment`), эти поля остаются пустыми.

2. **Обогащение — ручной пост-процесс.** Администратор должен запустить `artisan venues:enrich-addresses` вручную после импорта. Нет автоматического триггера.

3. **Нет верификации данных через Dadata при импорте.** Dadata не используется для проверки ИНН/ОГРН, названия или юридического адреса организации в момент создания записи. Верификация (`organizations:enrich-from-dadata`) — отдельная ручная операция.

4. **ImportController требует `geo_lat`/`geo_lon` как required.** Валидация на строке 82: `'venues.*.geo_lat' => 'required|numeric'`. Но Harvester-пайплайн не извлекает координаты (ИИ работает с текстом, а не с картами). Это **несовместимость контрактов**.

### 3.3. Harvester-сторона

В Python-пайплайне Dadata **не реализована** (Sprint 2+). В `config/settings.py` есть плейсхолдеры для ключей, но модуля `enrichment/` нет. Промпт (`organization_prompt.py`, правило 6) специально инструктирует LLM: "Если адрес неполный — добавь в address_raw как есть (Dadata нормализует позже)".

---

## 4. Статусная модель и decision routing

### 4.1. Текущая реализация (ImportController)

```php
private function determineStatus(array $aiMetadata): string
{
    if ($aiMetadata['decision'] === 'rejected')     → 'rejected'
    if ($aiMetadata['decision'] === 'accepted') {
        if ($confidence >= 0.85 && $worksWithElderly) → 'approved'   // Smart Publish
        else                                          → 'pending_review'
    }
    fallback                                          → 'draft'
}
```

### 4.2. Несовместимость с новым пайплайном

| Параметр | ImportController ожидает | Новый пайплайн отправляет |
|----------|------------------------|---------------------------|
| `ai_metadata.decision` | `accepted` \| `rejected` | `accepted` \| `rejected` \| **`needs_review`** |
| `venues.*.geo_lat` | **required** | **не предоставляется** |
| `venues.*.geo_lon` | **required** | **не предоставляется** |
| `contacts` (phones, emails) | Не принимается (TODO) | Предоставляется в payload |
| `short_title` | Не принимается | Предоставляется |
| `target_audience` | Не принимается | Предоставляется |
| `suggested_taxonomy` | Не принимается | Предоставляется |
| `site_urls`, `vk_group_url` | Не принимается | Предоставляется |

Валидация `ImportController` **отклонит** новый payload из-за `needs_review` в decision и отсутствия координат в venues.

---

## 5. Стратегии и области применения: за пределами org_website

### 5.1. Реализованные стратегии

| Стратегия | Модуль | Статус |
|-----------|--------|--------|
| **CSS-шаблон** (0 токенов) | `strategy_router.py` → `JsonCssExtractionStrategy` | Реализован, шаблонов нет (пустая директория `css_templates/`) |
| **LLM через Crawl4AI** (legacy) | `strategy_router.py` → `LLMExtractionStrategy` | Реализован, используется `base_system_prompt.py` + `RawOrganizationData` |
| **Regex-извлечение** (0 токенов) | `regex_strategy.py` | Реализован: телефоны, email, ИНН, ОГРН |
| **Полиморфная классификация** (новый) | `processors/organization_processor.py` | Реализован (данная сессия), не подключён к pipeline |

### 5.2. Типы источников в системе (Source.kind)

| kind | Описание | Реализован в Harvester? |
|------|----------|------------------------|
| `org_website` | Официальный сайт организации | Да (CLI `run_single_url.py`) |
| `registry_sfr` | Реестр СФР (ЦОСП и др.) | Нет (только schema в `HarvestInput`) |
| `registry_minsoc` | Реестр Минсоцзащиты | Нет |
| `vk_group` | VK-группа организации | Нет |
| `tg_channel` | Telegram-канал | Нет |
| `api_json` | Внешний API (JSON) | Нет |

Текущий пайплайн обрабатывает **только `org_website`**. Остальные типы описаны в схемах, но не реализованы.

### 5.3. Неиспользуемые области архитектуры

| Компонент | Статус | Файл/директория |
|-----------|--------|-----------------|
| `enrichment/` | Не создан | Планировался Sprint 2: classifier, Dadata, payload builder |
| `workers/` | Не создан | Планировался Sprint 3: Celery async |
| `core_client/` | Не создан | Планировался Sprint 2: HTTP-клиент к Core API |
| Staging-таблицы | Не созданы | Описаны в архитектурном документе |
| Diff-анализ | Не реализован | Описан в архитектурном документе |
| `importBatch()` | Заглушка | Возвращает `job_id: "placeholder"` |
| Individual import | Не реализован | `throw RuntimeException` |
| Event instances (RRule) | Не реализован | TODO в ImportController:205 |
| Auth middleware для internal API | Отсутствует | TODO в routes/api.php:16 |

---

## 6. Итоговая карта пробелов

### 6.1. Критические (блокируют полноценную работу пайплайна)

| # | Проблема | Где | Последствие |
|---|----------|-----|-------------|
| **G1** | Дедупликация организаций без ИНН всегда создаёт дубли | `ImportController:296` | Загрязнение БД при повторных прогонах |
| **G2** | Дедупликация событий отсутствует полностью | `ImportController:176` | Каждый импорт = новое событие |
| **G3** | `source_reference` не сохраняется в БД | `ImportController` | Невозможно отследить происхождение записи |
| **G4** | Нет GET-эндпоинта для lookup существующей записи | Отсутствует | Harvester не может вычислить `existing_entity_id` |
| **G5** | `needs_review` не принимается валидацией | `ImportController:65` | Новый пайплайн не может отправить промежуточный decision |
| **G6** | `geo_lat`/`geo_lon` обязательны, но Harvester их не предоставляет | `ImportController:82` | Venues без координат отклоняются валидацией |

### 6.2. Важные (снижают качество данных)

| # | Проблема | Где | Последствие |
|---|----------|-----|-------------|
| **G7** | Dadata не вызывается при импорте | `ImportController:380-411` | fias_id, region_iso остаются NULL до ручного обогащения |
| **G8** | Контакты (phones, emails) не принимаются API | `ImportController:370-371` | Извлечённые контакты теряются |
| **G9** | Нет auth middleware на internal API | `routes/api.php:16` | Любой может слать POST на /import |
| **G10** | `suggested_taxonomy` не принимается | `ImportController` | Предложения новых терминов теряются |

### 6.3. Желательные (для полноценной платформы)

| # | Проблема | Где |
|---|----------|-----|
| **G11** | Staging-таблицы не созданы | Архитектура описана, не реализована |
| **G12** | Нет Celery/async обработки | `workers/` не существует |
| **G13** | Только `org_website` как источник | Остальные kind не реализованы |
| **G14** | Individual import не реализован | `ImportController:353` |

---

## 7. Рекомендуемая последовательность устранения пробелов

### Фаза 1 — Контрактная совместимость (без рефакторинга)

1. **G5** — Добавить `needs_review` в валидацию `ImportController`: `'ai_metadata.decision' => 'in:accepted,rejected,needs_review'`
2. **G6** — Сделать `geo_lat`/`geo_lon` nullable: `'venues.*.geo_lat' => 'nullable|numeric'`
3. **G8** — Принять `contacts` в payload, сохранять в `Organizer.contact_phones/contact_emails`

### Фаза 2 — Идемпотентность

4. **G3** — Добавить колонку `source_reference` в таблицы `organizations`, `events` (или отдельную связующую таблицу)
5. **G4** — Создать `GET /api/internal/organizers?source_id=X&source_item_id=Y` для lookup
6. **G1** — Использовать `(source_reference)` или `(inn)` как ключ `updateOrCreate` (с fallback на `title_hash` при отсутствии обоих)
7. **G2** — Аналогично для событий: `(source_reference)` или `(organizer_id + title_hash)`

### Фаза 3 — Dadata-интеграция в пайплайн

8. **G7** — Вызывать `VenueAddressEnricher` в `processVenues()` или dispatcher (queued job после создания venue)
9. Реализовать `enrichment/dadata_client.py` в Harvester (Python-сторона)

### Фаза 4 — Расширение

10. **G10** — Принять `suggested_taxonomy`, сохранять в отдельную таблицу для модерации
11. **G9** — Добавить auth middleware
12. **G13** — Реализовать парсеры для `registry_sfr`, `vk_group` и т.д.
