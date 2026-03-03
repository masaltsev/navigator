# Ревизия архитектуры Harvester и план рефакторинга

- **Дата:** 2026-02-25
- **Область:** Harvester (ai-pipeline), Core API (backend), унификация потоков обогащения
- **Источник истины:** `docs/Navigator_Core_Model_and_API.md`, `docs/Harvester_v1_Development_Plan.md`, `ai-pipeline/harvester/docs/reports/2026-02-25__source-crud-api-auto-enrich.md`, `2026-02-25__unified-enrichment-aggregators.md`

---

## 1. Цель ревизии

Оценить, насколько унифицирована логика работы с тремя сценариями:

| Кейс | Описание | Идеальный поток |
|------|----------|-----------------|
| **А** | Организация в базе, есть корректный источник `org_website` | Получить URL → краул → описание/категории → Dadata → создание/обновление организации, организатора, площадки, источника |
| **Б** | Организация в базе, источник битый | Поиск/исправление URL → верификация → тот же поток, что в А |
| **В** | Организацию нужно достать из агрегатора (СО НКО, ФПГ, Silver Age) | Парсинг реестра → фильтр → для каждой организации: поиск сайта/данных → тот же поток (описание, категории, Dadata, создание/обновление) |

Вывод: после этапа «получил данные / принял решение по организации» поток действительно сходится к одному ядру (OrganizationProcessor → Dadata → import/organizer, создание source). Но **точки входа, оркестрация и обновление состояния источников разъединены**, есть дублирование кода и пропуски в контрактах Core.

---

## 2. Текущее состояние потоков

### 2.1 Кейс А: организация в базе, валидный org_website

**Триггер:** Плановый обход (Laravel Scheduler → Harvester).

**Фактическая цепочка:**

1. **Core:** Нет эндпоинта «источники к обходу». В плане заложен `GET /api/internal/sources?due=true` (выбор по `last_crawled_at + crawl_period_days`). Реализован только `GET /api/internal/sources?organizer_id=UUID` — список по организатору. То есть Laravel не может запросить «все источники, которые пора обойти».
2. **Harvester:** `POST /harvest/run` принимает готовый список `{url, source_id, ...}`. Кто и откуда его формирует — не определено (ожидается, что Core отдаст due sources; такого API нет).
3. **Обработка:** `workers/tasks.crawl_and_enrich` → `_run_pipeline()`: MultiPageCrawler → OrganizationProcessor → Dadata → `import_organizer`. Отдельно в коде **нигде не вызывается** `core_client.update_source(source_id, last_status=..., ...)`. Статус и дата обхода источника в Core после краула не обновляются.
4. **Core PATCH /sources/{id}:** принимает `last_status`, но не принимает `last_crawled_at` — поля в БД есть, в контроллере обновления нет.

**Итог по кейсу А:** Поток «краул → классификация → Core» есть, но нет выдачи due sources из Core и нет обновления статуса/даты обхода источника после выполнения задачи.

---

### 2.2 Кейс Б: организация в базе, источник битый

**Триггер:** Ручной/скриптовый запуск (аудит битых URL).

**Цепочка:**

1. **enrich_sources.py** (режимы `--fix-urls`, `--fix-urls-verified`): загрузка списка из JSON → для каждой записи `EnrichmentPipeline.enrich_broken_url()` или `fix_broken_url()` → верификация → при tier AUTO вызывается `_run_full_harvest()` (то же ядро: MultiPageCrawler + OrganizationProcessor + Dadata).
2. **Результаты:** пишутся в JSON. Применение к БД — через **patch_sources.py**, который работает **напрямую с PostgreSQL** (psycopg2): обновляет `sources.base_url`, при необходимости создаёт записи в `organizations`/`organizers`. Core API (PATCH /sources, синхронизация `site_urls`) не используется.

**Итог по кейсу Б:** Логика поиска/верификации и полного harvest унифицирована с EnrichmentPipeline, но применение изменений идёт в обход Core API. Риски: рассинхрон `site_urls`, разное поведение при конфликтах, нет единой точки истины для обновления источников.

---

### 2.3 Кейс В: организация из агрегатора (СОНКО, ФПГ, Silver Age)

**Триггер:** Импорт реестров (CLI/Celery по расписанию).

**Цепочка (после унификации 2026-02-25):**

1. Парсинг XLSX/веба → фильтрация → группировка по организации.
2. Для каждой организации: `lookup_organization(inn, source_reference)` → при совпадении `_update_matched_org()` (дополнение описания и ai_source_trace).
3. При отсутствии в Core: `EnrichmentPipeline.enrich_missing_source(..., additional_context=context, source_kind=registry_*)` → при успехе `import_organizer` + `create_source` через Core API.

**Итог по кейсу В:** От этапа «поиск сайта + верификация» всё идёт через общий EnrichmentPipeline и Core API. Унификация здесь достигнута; точки входа различаются только способом получения списка организаций (парсеры агрегаторов).

---

## 3. Выявленные разрывы и риски

### 3.1 Критические

| # | Проблема | Где | Последствие |
|---|----------|-----|-------------|
| **R1** | Нет API «источники к обходу» | Core: только `GET /sources?organizer_id=UUID` | Невозможно автоматически запускать плановый harvest: неоткуда взять список due sources для POST /harvest/run. |
| **R2** | После краула не обновляется статус источника | Harvester: `_run_pipeline()` не вызывает `update_source()` | В Core не фиксируются `last_status` и факт обхода; повторные запуски не могут опираться на `last_crawled_at`. |
| **R3** | Core PATCH /sources не обновляет `last_crawled_at` | SourceController::update() | Даже при вызове update_source из Harvester дата обхода не сохранится. |
| **R4** | Обновление битых источников мимо Core API | patch_sources.py → psycopg2 | Дубликаты логики, риск расхождения `site_urls`, обход валидации и бизнес-правил Core. |

### 3.2 Важные (архитектурные и поддерживаемость)

| # | Проблема | Где | Рекомендация |
|---|----------|-----|--------------|
| **R5** | Дублирование «полного harvest» | `workers/tasks._run_pipeline()` vs `EnrichmentPipeline._run_full_harvest()` | Один общий модуль «run harvest from URL» (например, вызов из tasks и из enrichment_pipeline), чтобы не разъезжались логика и контракт. |
| **R6** | Три точки входа «crawl → classify → Core» | run_single_url.py, tasks._run_pipeline, _run_full_harvest | Свести к одному ядру (например, `harvest.run_organization_harvest(url, source_id, ...)`) с разными обёртками (CLI, Celery, EnrichmentPipeline). |
| **R7** | Нет единого способа «обновить URL источника» | Core PATCH vs patch_sources (прямая БД) | Все изменения источников — только через Core API; patch_sources перевести на вызовы PATCH /sources (и при необходимости GET organizers/sources по source_id). |

### 3.3 Желательные

| # | Проблема | Где |
|---|----------|-----|
| **R8** | Event harvesting вызывается отдельно (POST /harvest/events) | Отдельный сценарий; можно оставить как есть, но документировать связь с обходом организаций. |
| **R9** | Виды источников в Core (kind) не полностью совпадают с агрегаторами | В SourceController store/update: `org_website,vk_group,ok_group,tg_channel` — нет `registry_fpg`, `registry_sonko`, `platform_silverage`. При создании source из агрегаторов может потребоваться расширение enum или отдельная политика. |

---

## 4. План рефакторинга

### Фаза 1: Core API — закрытие пробелов (критично для кейсов А и Б)

1. **Эндпоинт due sources (R1)**  
   - В Core: добавить поддержку запроса «источники, которые пора обойти».  
   - Вариант 1: `GET /api/internal/sources?due=true&limit=100` — выборка по `is_active = true` и `last_crawled_at + crawl_period_days <= NOW()` (или `last_crawled_at IS NULL`), с лимитом.  
   - Вариант 2: отдельный маршрут `GET /api/internal/sources/due?limit=100`.  
   - В ответе: массив записей с полями, нужными Harvester: `id`, `base_url`, `organizer_id`, `source_item_id` (если есть), `existing_entity_id` (organizer_id для привязки).  
   - Обновить описание в `docs/Navigator_Core_Model_and_API.md`.

2. **Обновление last_crawled_at и last_status (R2, R3)**  
   - В `SourceController::update()` (PATCH /sources/{id}) добавить приём и сохранение `last_crawled_at` (timestamp, опционально).  
   - В Harvester после успешного/неуспешного выполнения `crawl_and_enrich`: вызывать `core_client.update_source(source_id, last_status="success"|"error", last_crawled_at=...)`. Для этого в `NavigatorCoreClient.update_source()` добавить параметр `last_crawled_at` (и при необходимости в Core — обновление этого поля в транзакции с остальными полями).

### Фаза 2: Единая точка обновления источников (кейс Б)

3. **Перевод patch_sources на Core API (R4, R7)**  
   - Заменить прямые запросы к БД в `patch_sources.py` на вызовы Core API:  
     - Для обновления URL: `PATCH /api/internal/sources/{id}` с `base_url` (и при необходимости `last_status`).  
     - Если нужен organizer_id по source_id: либо добавить в Core `GET /api/internal/sources/{id}` (минимальная информация), либо получать список через существующие эндпоинты по данным из входного JSON.  
   - Убрать зависимость от psycopg2 в patch_sources (или оставить только для read-only аудита, если потребуется).  
   - Проверить сценарии: только AUTO, только approved REVIEW, интерактивное утверждение — все должны обновлять источник через PATCH.

### Фаза 3: Унификация ядра «harvest по URL» (R5, R6)

4. **Общий модуль «run organization harvest»**  
   - Выделить одну функцию/класс, например в `harvest/` или `processors/`: вход — URL, source_id, source_item_id, existing_entity_id, опции (multi_page, enrich_geo, additional_context, source_kind); выход — результат классификации + payload для Core (и при необходимости готовый ответ Core).  
   - Внутри: MultiPageCrawler (или альтернатива) → OrganizationProcessor → Dadata (если enrich_geo) → сборка payload.  
   - Подключить этот модуль:  
     - из `workers/tasks._run_pipeline()` — вместо текущей inline-логики;  
     - из `EnrichmentPipeline._run_full_harvest()` — вместо дублирующего кода;  
     - из `run_single_url.py` — как основной путь «crawl + classify + optional geo + optional Core».  
   - Обновление источника (last_status, last_crawled_at) выполнять в одном месте (например, в tasks после вызова общего модуля), по source_id из аргументов задачи.

5. **Документирование потока**  
   - В `harvester/docs/` (или в `docs/`) описать схему: три кейса (А — плановый обход, Б — битый URL, В — агрегатор), где поток расходится и где сходится, и что после «получил данные / принял решение» все идут через общий harvest → import_organizer (+ create_source при создании).

### Фаза 4 (по необходимости)

6. **Расширение kind источников в Core (R9)**  
   - Если агрегаторы создают источники с kind `registry_fpg` / `registry_sonko` / `platform_silverage`, в Core в валидации store/update добавить эти значения (или вынести kind в справочник/конфиг).  
   - Убедиться, что `syncSiteUrls` и прочая логика не ломаются для не-org_website (как сейчас и задумано).

7. **Интеграция Scheduler с due sources**  
   - В Laravel: по расписанию вызывать `GET /api/internal/sources?due=true&limit=N` (или `/sources/due`), затем формировать тело для `POST /harvest/run` и вызывать Harvester. Либо вынести вызов в отдельную команду/ job и описать в документации.

---

## 5. Краткая сводка

- **Унификация по сути есть:** от этапа «есть URL / верифицированный кандидат» и до «описание, категории, Dadata, организация, организатор, площадка, источник» все сценарии опираются на OrganizationProcessor и Core API (import/organizer, create_source). Агрегаторы уже переведены на общий EnrichmentPipeline с контекстом.
- **Критические разрывы:** в Core нет выдачи «источников к обходу», после краула не обновляются статус и дата источника, PATCH не трогает `last_crawled_at`, а исправление битых URL применяется к БД в обход Core.
- **Рефакторинг:** (1) добавить в Core эндпоинт due sources и поддержку `last_crawled_at` в PATCH; (2) в Harvester вызывать update_source после crawl_and_enrich; (3) перевести patch_sources на PATCH /sources; (4) выделить общее ядро «harvest по URL» и использовать его в tasks, EnrichmentPipeline и run_single_url; (5) зафиксировать схему потоков в документации.

После выполнения фаз 1–3 кейсы А и Б будут идти в одну струю с точки зрения API и обновления состояния, а поддержка и расширение (в т.ч. новые агрегаторы) упростятся.
