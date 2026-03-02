# Технологический стек и логика работы Навигатора (краткий обзор для техспециалистов)

**Дата:** 2026-02-27  
**Область:** архитектура, стек, потоки данных  
**Источники:** `docs/Navigator_Core_Model_and_API.md`, `docs/2026-02-26__test-server-deployment-options.md`, `ai-pipeline/harvester/docs/event_ingestion_pipeline.md`, `ai-pipeline/harvester/docs/harvest-flows-a-b-c.md`, `ai-pipeline/harvester/docs/aggregators_guide.md`

---

## 1. Назначение системы

«Навигатор здорового долголетия» — платформа для связи пользователей (пожилых людей, родственников, специалистов) с организациями и мероприятиями в сфере серебряной экономики. Целевая парадигма: **Answer Instead of Search** — система подбирает релевантные организации, события и статьи по запросу/проблеме, а не только каталог с фильтрами.

Два основных блока: **ядро (Core)** — хранение и API; **Harvester** — сбор, обогащение и классификация данных с помощью ИИ.

---

## 2. Технологический стек

| Компонент | Путь | Стек |
|-----------|------|------|
| **Backend (Navigator Core)** | `backend/` | Laravel 12, PHP 8.2+, PostgreSQL (с PostGIS для гео), Redis (очереди/кэш), Node/npm (Vite) |
| **Harvester (AI pipeline)** | `ai-pipeline/harvester/` | Python 3.12, FastAPI, Celery; Crawl4AI + Playwright Chromium; DeepSeek API; опционально Dadata, Yandex Search |

**Общие сервисы:** PostgreSQL (основная БД Core, для venues нужен PostGIS), Redis (очереди Celery, при необходимости Laravel queue/cache).

**Связка Core ↔ Harvester:** Harvester вызывает Core API (`CORE_API_URL`, `CORE_API_TOKEN`). Laravel экспортирует справочники в JSON: `php artisan seeders:export-json` → `ai-pipeline/harvester/seeders_data/`. Запуск сбора может инициировать Laravel (например, Scheduler) или внешний оркестратор.

---

## 3. Доменная модель (ядро)

- **Справочники (dictionaries):** ThematicCategory, Service, OrganizationType, SpecialistProfile, OwnershipType, CoverageLevel, EventCategory — неизменяемый фундамент; ИИ только маппит на их id/code.
- **Полиморфные организаторы:** таблица `organizers` (organizable_type / organizable_id) → `organizations` (юрлица, ИНН/ОГРН, сайты, соцсети) или `initiative_groups` (неформальные сообщества). У организаций — флаги и метрики ИИ: `works_with_elderly`, `ai_confidence_score`, `ai_explanation`, `ai_source_trace`.
- **Площадки:** `venues` — адрес, ФИАС/КЛАДР, координаты (PostGIS Point).
- **Мероприятия:** `events` (organizer_id, rrule_string, attendance_mode) + `event_instances` (раскрытие RRule на экземпляры).
- **Контент:** `articles` — связь с тематическими категориями и услугами для рекомендаций.
- **Источники:** `sources` — привязка к организатору, тип (org_website, registry_*), URL, last_crawled_at, статус.

Подробно: `docs/Navigator_Core_Model_and_API.md`.

---

## 4. Логика работы Harvester

### 4.1 Общее ядро обогащения организаций

Все сценарии сходятся к **`run_organization_harvest`**: краул сайта (Crawl4AI/Playwright) → извлечение текста → классификация через DeepSeek (OrganizationProcessor) → опционально Dadata (адрес, реквизиты) → сборка payload → Core API `import_organizer`, обновление/создание `source`.

### 4.2 Три потока (кейсы А, Б, В)

- **А — плановый обход:** Core отдаёт список due sources (`GET /api/internal/sources/due`). Celery-задача `crawl_and_enrich` для каждого источника → общее ядро → `import_organizer` + `PATCH` source (last_status, last_crawled_at).
- **Б — битый URL:** По организации без рабочего сайта или с неверным URL запускается поиск (DuckDuckGo/Yandex) + верификация; при нахождении `verified_url` — тот же `run_organization_harvest`; применение через скрипт `patch_sources` → Core API `PATCH /sources/{id}`.
- **В — агрегаторы:** Импорт из реестров (ФПГ, СО НКО, Silver Age). Парсинг XLSX/веб → поиск сайта и контекста → при наличии URL тот же `run_organization_harvest` с `additional_context`; при создании новой организации — при необходимости создаётся source (AUTO tier).

### 4.3 Мероприятия (Event Ingestion Pipeline)

Единый пайплайн для всех источников событий (сайт организации, Silver Age, в перспективе VK/Telegram):

1. Адаптер приводит сырые данные к **RawEventInput** (source_reference, title, raw_text, source_url, source_kind, date_text или start/end ISO, location, is_online и т.д.).
2. Парсинг дат (русский текст → ISO), классификация через **EventProcessor** (DeepSeek) → категории, target_audience, ai_metadata.
3. Сборка payload для Core → `POST /api/internal/import/event`.

Конфликты/низкая уверенность → маршрутизация на ручную проверку (needs_review).

### 4.4 Агрегаторы

- **ФПГ** — XLSX проектов президентских грантов; фильтрация по направлению/ключевым словам; идентификация по ИНН/ОГРН.
- **СО НКО** — XLSX реестра Минэкономразвития; фильтрация по ОКВЭД/ключевым словам.
- **Silver Age** — парсинг silveragemap.ru (практики + мероприятия); идентификация по названию; мероприятия проходят Event Ingestion Pipeline.

Для организаций без готового URL используется поиск (DuckDuckGo/Yandex) + верификация; один запрос Dadata (suggest_party) сохраняется и переиспользуется по пайплайну.

---

## 5. Краткая схема данных и интеграций

```
[Реестры / сайты орг. / поиск]
         ↓
   Harvester (Python)
   - Crawl4AI, DeepSeek, Dadata
   - Celery, Event Ingestion
         ↓
   Core API (Laravel)
   - import_organizer, import_event
   - PATCH sources, seeders export
         ↓
   PostgreSQL (PostGIS) ← фронты, партнёры, мини-приложения
```

Подробные потоки и диаграммы: `ai-pipeline/harvester/docs/harvest-flows-a-b-c.md`, `ai-pipeline/harvester/docs/event_ingestion_pipeline.md`, `ai-pipeline/harvester/docs/aggregators_guide.md`.
