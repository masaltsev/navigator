# План разработки Harvester v1

> На основе: **Harvester_v1_Final Spec.md**, **Navigator_Core_Model_and_API.md**, **AI_Pipeline_Navigator_Plan.md**  
> Дата: 21 февраля 2026  
> **Режим:** реализация под руководством продукта/архитектора; исполнитель — senior Python/AI (агент).

---

## 0. Как я работаю (агент под твоим руководством)

**Роль:** Senior Python / AI разработчик. Пишу код, тесты и минимальную документацию в `ai-pipeline/harvester/`. Ориентируюсь на спецификации и этот план.

**Ты задаёшь направление:** приоритет задач, решения по API/контрактам Core, выдача ключей (DeepSeek, Dadata), ревью и «стоп, делаем иначе».

**Как я действую по шагам:**
- Беру задачи из спринтов по порядку; перед началом спринта кратко подтверждаю объём и что нужно от тебя (ключи, моки, контракт API).
- После логичных блоков (например, 1.1–1.5) делаю явный checkpoint: что сделано, что проверить. Не ухожу в следующий спринт без твоего «ок» или явного запроса.
- Если в спецификации неоднозначность (например, формат `parse_profile_config` или поля ответа Core) — предлагаю вариант и спрашиваю утверждение.
- Тесты пишу сразу рядом с кодом (unit — без сети/LLM; интеграционные — только по твоему запросу или если ты даёшь стенд).
- Секреты не коммичу: только `.env.example` с плейсхолдерами, в коде — чтение из env.

**Принципы, которых придерживаюсь:**
- Pydantic-first: все DTO и конфиги — модели, не голые `dict`.
- Коды справочников только из сидеров; маппинг — в `classifier.py`, LLM не возвращает коды.
- Три уровня экстракции: Regex (0 токенов) → CSS-шаблон (0 токенов) → LLM (DeepSeek).
- Async-first для I/O; Celery только для оркестрации и retry.
- Harvester не решает staging/diff/immutability — только собирает payload и шлёт в Core.

**Что мне нужно от тебя перед стартом (один раз):**
- Подтверждение, что начинаем со Спринта 1 (или с другой задачи, если приоритет другой).
- Доступ к ключам: `DEEPSEEK_API_KEY`, при необходимости `DADATA_*`, `CORE_API_TOKEN` — в .env у тебя; я работаю с `.env.example` и инструкцией в README.
- Ответ по Core: internal API уже есть (URL + контракт) или сначала делаем всё с моками и потом подключаем.

---

## 1. Цель и границы Phase 1

**Цель:** обогащение уже заведённых в базу организаций по источникам типа `org_website` (официальные сайты в таблице `sources`). Harvester обходит сайты, извлекает структурированные данные и выравнивает их по реляционной модели Navigator Core через закрытые справочники.

**Вне Phase 1:** агрегаторы (ФПГ, реестр СО НКО, Добро.рф) — Phase 2.  
**UPD:** полиморфные промпты реализованы досрочно (Sprint 1) — см. §10.

**Критерии готовности Phase 1:**
- CLI: один URL → Crawl4AI + DeepSeek → `RawOrganizationData` в JSON.
- E2E: URL → полный pipeline → JSON в Core API (staging).
- Celery batch: 50 URL обрабатываются воркером; CSS-шаблоны работают без LLM-токенов.
- Первый полный проход по всем ~5 000 org_website, результаты в staging Core.

---

## 2. Зависимости и предпосылки

### 2.1 Со стороны Navigator Core (Laravel)

| # | Компонент | Описание | Статус |
|---|-----------|----------|--------|
| 1 | **Internal API** | `POST /api/internal/import/organizer` — приём payload от Harvester (staging, diff, immutability на стороне Core) | Проверить/реализовать |
| 2 | **Source loader** | `GET /api/internal/sources?due=true` — выбор источников к обходу по `last_crawled_at + crawl_period_days` | Проверить/реализовать |
| 3 | **Source status** | Обновление `last_status`, `last_crawled_at` по source_id (PATCH или отдельный endpoint) | Уточнить контракт |
| 4 | **Harvest trigger** | `POST /harvest/run` с `{"sourceIds": ["uuid1", ...]}` — вызов из Laravel Scheduler в сторону Harvester | Реализовать в Core или в Harvester |
| 5 | **Таблицы** | `sources`, `parse_profiles` с полями из Navigator_Core_Model_and_API (kind, base_url, entry_points, parse_profile_id, last_status, crawl_period_days и т.д.) | Проверить миграции |
| 6 | **Справочники** | ThematicCategory, Service, OrganizationType, SpecialistProfile, OwnershipType — сидеры как single source of truth | Есть (см. git status) |

### 2.2 Со стороны инфраструктуры

- Python 3.12, Redis, доступ к DeepSeek API (LiteLLM), Dadata API.
- Опционально: Firecrawl Cloud (fallback для ~10% сайтов под защитой).

### 2.3 Связь с AI Pipeline Plan

- **Schema-Constrained Extraction:** только коды из сидеров; маппинг в Harvester делает `classifier.py`, не LLM.
- **Staging / Diff / Immutability:** реализуются в Laravel при обработке `POST /api/internal/import/organizer`; Harvester только формирует payload.
- **Полиморфные промпты:** ~~в Phase 1 — один базовый промпт (stub)~~ **UPD:** реализованы в Sprint 1 — `organization_prompt.py`, `event_prompt.py`, 3 паттерна (медицина / соцзащита / активное долголетие).

---

## 3. Структура репозитория (напоминание)

```
navigator/
├── backend/                    # Laravel
│   └── app/Console/Commands/
│       └── ExportSeedersJson.php   # новая команда
├── ai-pipeline/
│   └── harvester/               # Python-модуль
│       ├── pyproject.toml, .env
│       ├── seeders_data/       # JSON из Laravel
│       ├── config/
│       ├── schemas/
│       ├── strategies/
│       ├── prompts/            # stub + реестр
│       ├── enrichment/
│       ├── workers/
│       ├── core_client/
│       ├── scripts/
│       └── tests/
└── docs/
```

---

## 4. Пошаговый план (спринты)

### Спринт 1 (недели 1–2): Скелет и первый краул

| # | Задача | Результат | Часы |
|---|--------|-----------|------|
| 1.1 | Создать `ai-pipeline/harvester/`, `pyproject.toml`, `.env.example` | Проект с зависимостями (crawl4ai, pydantic, celery, httpx, tenacity, structlog) | 2 |
| 1.2 | `config/settings.py` (Pydantic Settings), `config/llm_config.py` (DeepSeek через LiteLLM) | Конфиг из env, фабрика LLMConfig | 2 |
| 1.3 | Laravel: команда `php artisan seeders:export-json` → JSON в `ai-pipeline/harvester/seeders_data/` | ExportSeedersJson.php | 3 |
| 1.4 | `config/seeders.py` — загрузка JSON в Pydantic, `child_categories` для тематик | NavigatorSeeders, load_seeders() | 2 |
| 1.5 | `schemas/extraction.py` (RawOrganizationData), `schemas/navigator_core.py` (OrganizationImportPayload, AiMetadata, ClassificationPayload, VenuePayload) | Схемы, совместимые с Core API | 3 |
| 1.6 | `strategies/strategy_router.py` — выбор LLM vs CSS, LLMExtractionStrategy с RawOrganizationData | CrawlerRunConfig для одного URL | 4 |
| 1.7 | `strategies/regex_strategy.py` — телефоны, email, ИНН, ОГРН (0 токенов) | ContactExtraction | 2 |
| 1.8 | `prompts/base_system_prompt.py` (stub), `prompts/prompt_registry.py` — инъекция сидеров в системный промпт | Единый промпт для org_website | 3 |
| 1.9 | `scripts/run_single_url.py` — CLI: URL → краул → JSON RawOrganizationData | Отладочный запуск одного URL | 2 |
| 1.10 | Тест на 5 реальных КЦСОН через CLI | Проверка цепочки Crawl4AI + DeepSeek → JSON | 4 |

**DoD спринта 1:** CLI принимает URL и выводит `RawOrganizationData` в JSON.

**От меня:** код в `ai-pipeline/harvester/` + Laravel-команда `ExportSeedersJson`; README с запуском CLI и переменными окружения.  
**Нужно от тебя:** (1) Запуск `php artisan seeders:export-json` после сидеров и размещение `seeders_data/` в репо или инструкция; (2) Для 1.10 — список из 5 тестовых URL КЦСОН или «бери из спецификации»; (3) Ключ DeepSeek в .env для проверки краула.  
**Checkpoint:** после 1.9 показываю вывод CLI на одном URL; после 1.10 — краткий отчёт по 5 URL (успех/ошибка, пример JSON).

---

### Спринт 2 (недели 3–4): Классификация и Core API

| # | Задача | Результат | Часы |
|---|--------|-----------|------|
| 2.1 | `enrichment/classifier.py` — маппинг на коды сидеров (услуги, тематики, типы орг., специалисты, ОПФ по аббревиатуре) | SeederClassifier, fuzzy match, OWNERSHIP_PREFIX_MAP | 6 |
| 2.2 | `enrichment/dadata_client.py` — геокодирование адресов | Метод geocode(addr) → fias_id, geo_lat, geo_lon | 3 |
| 2.3 | `enrichment/confidence_scorer.py` — ai_confidence_score, works_with_elderly, explanation | calculate_confidence(raw, classification) | 3 |
| 2.4 | `enrichment/payload_builder.py` — сборка OrganizationImportPayload (regex-обогащение контактов → classifier → Dadata → decision) | PayloadBuilder.build() | 4 |
| 2.5 | `core_client/api.py` — HTTP-клиент: GET sources?due=true, POST import/organizer, обновление статуса source | NavigatorCoreClient | 4 |
| 2.6 | E2E: URL → payload → POST /api/internal/import/organizer (проверка staging в Core) | Полный цикл до Core | 4 |
| 2.7 | Fixtures: HTML-снапшоты (например, КЦСОН, НКО) в `tests/fixtures/` | Тесты без живого краула | 3 |

**DoD спринта 2:** Один URL проходит полный pipeline до отправки JSON в Core API (staging).

**От меня:** classifier, dadata_client, confidence_scorer, payload_builder, core_client (HTTP), E2E-скрипт или расширение CLI (флаг «до Core»), fixtures для тестов.  
**Нужно от тебя:** (1) Контракт Core: точный URL и формат `POST /api/internal/import/organizer` (или OpenAPI/пример тела); способ обновить статус source (PATCH/отдельный endpoint); (2) Ключи Dadata и Core API в .env для E2E; (3) Решение: реальный Core или мок (я делаю мок-сервер/заглушку, если Core ещё нет).  
**Checkpoint:** показываю один полный payload, отправленный в Core (или в мок), и ответ; при расхождении контракта — правки по твоим правкам.

---

### Спринт 3 (недели 5–6): Multi-page, CSS, Celery

| # | Задача | Результат | Часы |
|---|--------|-----------|------|
| 3.1 | `strategies/multi_page.py` — обход главной + подстраниц (/uslugi, /kontakty, /o-nas и т.д.), слияние в один RawOrganizationData | MultiPageCrawler.crawl_organization() | 6 |
| 3.2 | Генерация CSS-шаблонов для 3–5 типовых КЦСОН (скрипт + ручная доводка или LLM один раз) | `schemas/css_templates/kcson_template.json` и др. | 4 |
| 3.3 | `strategies/css_strategy.py` — JsonCssExtractionStrategy, подключение в StrategyRouter по parse_profile_config | Выбор CSS вместо LLM где есть шаблон | 3 |
| 3.4 | Celery: `workers/celery_app.py`, `workers/tasks.py` — crawl_and_enrich(source_data), process_batch(source_ids) | Очередь Redis, retry, asyncio.run в таске | 4 |
| 3.5 | Docker: Dockerfile для harvester, docker-compose (harvester + redis) | Запуск воркера в контейнере | 4 |
| 3.6 | Batch-тест: 50 организаций через Celery | Убедиться в стабильности и отсутствии утечек | 4 |

**DoD спринта 3:** Celery-воркер обрабатывает batch из 50 URL; для части источников используются CSS-шаблоны (0 токенов).

**От меня:** multi_page crawler, скрипт генерации/шаблоны CSS, css_strategy в router, Celery app + tasks, Dockerfile + docker-compose.  
**Нужно от тебя:** (1) 3–5 примеров HTML страниц КЦСОН для генерации CSS-шаблона (или разрешение брать с указанных в спецификации URL); (2) Redis: локально или URL для подключения воркера; (3) Список 50 source_id/URL для batch-теста или «генерируй из Core GET sources».  
**Checkpoint:** вывод воркера на 5–10 задачах (логи, время, успех/ошибка); при необходимости — правки по твоим замечаниям перед полным batch 50.

---

### Спринт 4 (недели 7–8): Продакшен и первый полный проход

| # | Задача | Результат | Часы |
|---|--------|-----------|------|
| 4.1 | Structured logging (structlog), единый формат логов | Логи для отладки и аудита | 3 |
| 4.2 | Обработка ошибок, retry (tenacity) в критичных местах (Dadata, Core API, краул) | Устойчивость к сетевым сбоям | 3 |
| 4.3 | Метрики: стоимость токенов, success rate, время на источник (логи или простой счётчик) | Оценка первого прохода | 4 |
| 4.4 | Интеграция с Laravel: Scheduler вызывает Harvester (POST /harvest/run или постановка задач в Redis) | Регулярный запуск по due sources | 3 |
| 4.5 | Firecrawl Cloud fallback для сайтов под Cloudflare/DDoS-Guard (опционально) | Снижение доли неуспешных краулов | 4 |
| 4.6 | Первый полный проход: все org_website из Core | Обработка ~5 000 источников | 8 |
| 4.7 | Анализ результатов: распределение confidence, ручная выборочная проверка, настройка порогов (0.85 для auto-approve) | Отчёт и при необходимости донастройка | 4 |

**DoD спринта 4:** Все org_website обработаны; результаты в staging Core; пороги и мониторинг согласованы.

**От меня:** structlog, tenacity retry в нужных местах, простые метрики (логи/счётчики), интеграция с Laravel (вызов Harvester по расписанию), опционально Firecrawl fallback, скрипт/инструкция первого полного прохода, отчёт по результатам (распределение confidence, доля успехов, рекомендации по порогу).  
**Нужно от тебя:** (1) Решение по триггеру: Laravel дергает POST /harvest/run на Harvester или Harvester сам опрашивает Core (GET sources?due=true) и ставит задачи; (2) Порог auto-approve (0.85 по спецификации — ок или другой); (3) Запуск полного прохода и доступ к staging/логам для анализа.  
**Checkpoint:** после 4.6 — сводка (сколько обработано, success rate, примеры ошибок); после 4.7 — короткий отчёт и фиксация порогов в коде/конфиге.

---

## 5. Дополнительные задачи (сквозные)

**Делаю по умолчанию:**
- **Тесты:** unit для classifier, payload_builder, confidence_scorer на основе fixtures (без живого LLM и сети); при добавлении core_client — тесты с моком httpx.
- **Документация:** README в `ai-pipeline/harvester/` (установка, запуск CLI, воркер, переменные .env).
- **Безопасность:** только `.env.example` с плейсхолдерами; в коде — чтение из env, без хардкода секретов.

**По твоему запросу или после согласования:**
- Актуализация `backend/docs/API_TESTING_CHECKLIST.md` при появлении internal endpoints.
- Интеграционные тесты на реальном Core (если дашь стенд и разрешение).
- Расширение метрик (например, экспорт в файл/Prometheus).

---

## 6. Риски и митигации

| Риск | Митигация |
|------|-----------|
| Часть сайтов недоступна (блокировки, таймауты) | Firecrawl fallback; помечать last_status=error, не блокировать batch |
| Расхождение контракта Core API с payload | Сверить с Navigator_Core_Model_and_API (POST /api/internal/import/organizer), тесты на реальном ответе Core |
| Стоимость DeepSeek выше ожидаемой | CSS-шаблоны и regex снижают долю страниц с LLM; кэш системного промпта |
| Laravel internal API ещё не готов | Реализовать моки в Harvester; параллельно вести контракт в Core |

---

## 7. Оценка ресурсов

| Ресурс | Оценка |
|--------|--------|
| Человекочасы | ~120–140 ч (1 Python-разработчик, ~8 недель) |
| DeepSeek API | $8–15 за первый проход (~10K страниц) |
| Dadata | Бесплатный план (10K запросов/день) |
| Firecrawl (fallback) | $16/мес (Hobby) |
| Инфраструктура | VPS 2 vCPU / 4 GB + Redis (~$15/мес) |

---

## 8. Phase 2 (кратко)

После Phase 1:

- Новые `sources.kind`: `registry_fpg`, `registry_sonko`, `platform_dobro`.
- Новые стратегии обхода: `paginated_list`, `open_data_csv`.
- Логика `match_or_create` по ИНН/ОГРН для новых организаций из реестров.
- Полиморфные промпты по типу организации (КЦСОН, поликлиника, НКО) — по AI_Pipeline_Navigator_Plan.

Структуру Harvester перестраивать не требуется — расширение через новые стратегии и конфиги.

---

## 9. Чек-лист перед стартом

**Я проверяю в репо:**
- [ ] Есть ли уже `ai-pipeline/harvester/` или создаю с нуля.
- [ ] Сидеры в `backend/database/seeders/` (ThematicCategory, Service, OrganizationType, SpecialistProfile, OwnershipType) и модели с полями code/name/is_active.

**Нужно от тебя:**
- [ ] Решение: начинаем со Спринта 1 целиком или с конкретных задач (напр. только 1.1–1.5).
- [ ] Ключи: DeepSeek для краула (для 1.10); Dadata и Core — к началу Спринта 2 или работаем с моками.
- [ ] Core API: есть ли уже `POST /api/internal/import/organizer` и GET sources; если нет — делаю моки и подключаем позже.
- [ ] Redis: локально (docker/системный) или URL — к Спринту 3.

После твоего «поехали» и ответов по чек-листу начинаю Спринт 1.

---

## 10. Прогресс и статус спринтов

> Обновлено: 2026-02-24

### Спринт 1 — ЗАВЕРШЁН

| # | Задача | Статус | Заметки |
|---|--------|--------|---------|
| 1.1 | pyproject.toml, .env.example | **Done** | |
| 1.2 | config/settings.py, llm_config.py | **Done** | |
| 1.3 | ExportSeedersJson.php | **Done** | Экспорт 5 справочников с description/keywords |
| 1.4 | config/seeders.py | **Done** | |
| 1.5 | schemas/extraction.py, navigator_core.py | **Done** | |
| 1.6 | strategy_router.py | **Done** | Legacy: через LLMExtractionStrategy. Целевой пайплайн — OrganizationProcessor |
| 1.7 | regex_strategy.py | **Done** | |
| 1.8 | base_system_prompt.py, prompt_registry.py | **Done** | Legacy промпт; новый — organization_prompt.py |
| 1.9 | run_single_url.py CLI | **Done** | Переписан на новый пайплайн (Crawl4AI + OrganizationProcessor) |
| 1.10 | Тест на 5 реальных URL | **Done** | Отчёт: `harvester/docs/reports/2026-02-24__sprint1-10-crawl-test.md` |

**Сделано сверх плана Sprint 1:**

| Что | Файлы/отчёты |
|-----|-------------|
| Расширение онтологии (6 категорий, 8 услуг, 4 типа орг., 4 специалиста) | `navigator_ontology_update.md`, 2 миграции, 5 сидеров обновлены |
| Полиморфные промпты (было Phase 2) | `prompts/schemas.py`, `dictionaries.py`, `examples.py`, `organization_prompt.py`, `event_prompt.py` |
| OrganizationProcessor + DeepSeekClient | `processors/organization_processor.py`, `deepseek_client.py`, `event_processor.py` |
| 35 unit-тестов | `tests/test_schemas.py` (18), `tests/test_prompts.py` (17) |
| Архитектурный аудит entity lifecycle | `harvester/docs/reports/2026-02-24__entity-lifecycle-review.md` |
| Фаза A — контрактная совместимость ImportController | `backend/docs/reports/2026-02-24__import-controller-phase-a.md` |

**Архитектурные решения:**
- **Целевой пайплайн**: Crawl4AI (markdown only) → `OrganizationProcessor` → DeepSeek API (OpenAI SDK) → Pydantic `OrganizationOutput`. Legacy-пайплайн через `LLMExtractionStrategy` / LiteLLM — только для отладки краулинга (`--crawl-only`).
- **Классификация LLM-first**: LLM возвращает коды справочников напрямую (не fuzzy match). Post-hoc валидация в `_validate_codes()` с автокоррекцией перепутанных справочников.
- **Cache hit**: system prompt ~15K tokens кэшируется DeepSeek API (prefix caching). При batch ожидается >90% hit rate. Стоимость: ~$2.75 за 5 000 URL (в 3-5x дешевле прогноза).

### Спринт 2 — ПРЕДСТОИТ

**Что из Sprint 2 уже частично готово:**

| # | Задача по плану | Факт | Остаток |
|---|----------------|------|---------|
| 2.1 | classifier.py | Логика в OrganizationProcessor + промптах (LLM классифицирует напрямую) | Отдельный classifier.py не нужен — пересмотреть |
| 2.3 | confidence_scorer.py | AIConfidenceMetadata в schemas.py, decision routing в OrganizationProcessor | Пересмотреть — может быть не нужен |
| 2.4 | payload_builder.py | `to_core_import_payload()` в organization_processor.py | Пересмотреть — может быть не нужен |

**Что нужно сделать:**

| # | Задача | Статус |
|---|--------|--------|
| 2.2 | `enrichment/dadata_client.py` — геокодирование | Не начато. Ключи Dadata в .env |
| 2.5 | `core_client/api.py` — HTTP-клиент к Core | Не начато. Контракт Core API готов (ImportController обновлён) |
| 2.6 | E2E: URL → payload → POST в Core | Не начато. Блокировался G5/G6/G8 — теперь решены |
| 2.7 | Fixtures: HTML-снапшоты | Не начато |

---

## 11. Бэклог: отложенные задачи и TODO

> Все задачи, выявленные в ходе разработки Sprint 1, тестирования и аудита.
> Приоритет: 🔴 критический, 🟡 важный, 🟢 желательный.

### 11.1. Python-пайплайн (ai-pipeline/harvester)

| # | Приоритет | Задача | Источник | Когда |
|---|-----------|--------|----------|-------|
| **H1** | 🟡 | Multi-page стратегия: обход /kontakty, /o-nas, /uslugi, слияние markdown | Sprint 1.10 (P3, P7): адреса и email не извлекаются с подстраниц | Sprint 3 (3.1) |
| **H2** | 🟡 | Title: на сайтах без явного юрлица на главной LLM перефразирует название | Sprint 1.10 (P4): neurology.ru → «Российский центр неврологии» вместо ФГБНУ | Sprint 3 (multi-page) |
| **H3** | 🟡 | Firecrawl fallback для SPA-сайтов | Sprint 1.10 (P5): orateatr.com — Playwright не загружает SPA | Sprint 4 (4.5) |
| **H4** | 🟢 | `suggested_taxonomy` пустой во всех тестах | Sprint 1.10 (P6): LLM не предлагает новые термины | Донастройка few-shot примеров |
| **H5** | 🟢 | org_type_codes пустой для НКО/фондов | Sprint 1.10 ретест: после автокоррекции org_types = [] для «Образ жизни» | Добавить код НКО в org_types или few-shot пример |
| **H6** | 🟢 | Переключить `prompt_registry.py` на новые промпты | Polymorphic prompts report: legacy registry ещё используется strategy_router | Когда legacy-пайплайн будет полностью заменён |
| **H7** | 🟢 | Интеграционный тест с реальным DeepSeek на 3-5 URL через `OrganizationProcessor.process()` с оценкой cache hit rate | Polymorphic prompts report: рекомендация §7.1 | Sprint 2 (при E2E) |
| **H8** | 🟢 | Расширить few-shot примеры: пример rejected-организации (детсад, фитнес без маркера 55+) | Polymorphic prompts report: рекомендация §7.5 | Sprint 2 или 3 |

### 11.2. Backend / Core API (Laravel)

| # | Приоритет | Задача | Источник | Когда |
|---|-----------|--------|----------|-------|
| **B1** | 🔴 | Миграция: `source_reference` (string, indexed) в `organizations`, `events` | Entity lifecycle review (G1, G2, G3): дедупликация без ИНН создаёт дубли | До batch-прогона (Sprint 4) |
| **B2** | 🔴 | Дедупликация организаций: fallback ключ `source_reference` → `inn` → `title` | Entity lifecycle review (G1): `updateOrCreate(['inn' => null])` создаёт дубли | До batch-прогона (Sprint 4) |
| **B3** | 🔴 | Дедупликация событий: `updateOrCreate` по `(organizer_id, source_reference)` | Entity lifecycle review (G2): пустой match key → каждый импорт = новое событие | До batch-прогона (Sprint 4) |
| **B4** | 🟡 | Миграция: `short_title` (varchar 100) в `organizations` | Phase A report: поле принимается, но не сохраняется | Sprint 2 |
| **B5** | 🟡 | Конвертация `vk_group_url` → `vk_group_id` при импорте | Phase A report: в БД integer, из пайплайна приходит URL | Sprint 2-3 |
| **B6** | 🟡 | Auth middleware на internal API | Entity lifecycle review (G9): нет авторизации на `/api/internal/*` | Sprint 4 |
| **B7** | 🟡 | `GET /api/internal/organizers?source_id=X&source_item_id=Y` для lookup | Entity lifecycle review (G4): Harvester не может определить existing_entity_id | Sprint 2-3 |
| **B8** | 🟢 | Таблица `suggested_taxonomy_items` для модерации предложений от ИИ | Phase A report: suggested_taxonomy принимается, но не сохраняется | Sprint 3-4 |
| **B9** | 🟢 | Dadata при импорте: вызывать `VenueAddressEnricher` в `processVenues()` автоматически | Entity lifecycle review (G7): fias_id остаётся NULL до ручного обогащения | Sprint 3-4 |
| **B10** | 🟢 | Staging-таблицы для diff-анализа | Entity lifecycle review (G11): описаны в архитектуре, не реализованы | Phase 2 |

### 11.3. Обновлённые оценки ресурсов

По результатам Sprint 1.10:

| Ресурс | Прогноз (из §7) | Факт / уточнение |
|--------|-----------------|-------------------|
| DeepSeek API | $8–15 за 5 000 URL | **~$2.75** (при 75%+ cache hit, $0.0006/URL) |
| Время на 1 URL | не оценивалось | **~20s** (crawl 4s + LLM 16s) |
| Экстраполяция на 5 000 | — | ~28 часов последовательно; ~5 часов при 6 параллельных воркерах |

---

## 12. Для агента: старт сессии

В начале сессии проверяю:
1. **Текущий спринт и задачу** — смотрю §10 (прогресс) и §11 (бэклог).
2. **Checkpoint** — был ли подтверждён предыдущий блок; если нет, сначала показываю результат и жду «ок» или правки.
3. **Нужно от тебя** — из блока спринта: ключи, контракт API, список URL, решение по мокам/Redis и т.д. Если чего-то не хватает, спрашиваю или делаю разумные моки и помечаю в коде/README.
4. **Спеки** — при неясностях смотрю Harvester_v1_Final Spec и Navigator_Core_Model_and_API; при расхождении предлагаю вариант и прошу утвердить.
5. **Бэклог** — проверяю §11 на отложенные задачи, которые пора взять в работу.
