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
| 4.8 | Event harvesting: краулинг мероприятий с сайтов организаций (/news, /afisha) → EventProcessor | Двойной проход: Organization + Event с одного сайта | 8 |

**DoD спринта 4:** Все org_website обработаны; результаты в staging Core; пороги и мониторинг согласованы. Для пилотной выборки сайтов собраны мероприятия.

**От меня:** structlog, tenacity retry в нужных местах, простые метрики (логи/счётчики), интеграция с Laravel (вызов Harvester по расписанию), опционально Firecrawl fallback, скрипт/инструкция первого полного прохода, отчёт по результатам (распределение confidence, доля успехов, рекомендации по порогу), стратегия краулинга мероприятий (4.8).  
**Нужно от тебя:** (1) Решение по триггеру: Laravel дергает POST /harvest/run на Harvester или Harvester сам опрашивает Core (GET sources?due=true) и ставит задачи; (2) Порог auto-approve (0.85 по спецификации — ок или другой); (3) Запуск полного прохода и доступ к staging/логам для анализа; (4) Решение по event harvesting: нужны ли мероприятия в Phase 1 или Phase 2; приоритет и объём (все сайты или пилот на socinfo.ru).  
**Checkpoint:** после 4.6 — сводка (сколько обработано, success rate, примеры ошибок); после 4.7 — короткий отчёт и фиксация порогов в коде/конфиге; после 4.8 — пилотный прогон event harvesting на 10-20 сайтах.

#### Детализация задачи 4.8: Event Harvesting

**Проблема:** при краулинге организаций мы фильтруем `/news`, `/novosti`, `/afisha` как нерелевантные для извлечения контактов/адресов организации. Но эти страницы содержат анонсы мероприятий — Масленицы, мастер-классы, акции, школы ухода — которые релевантны для Навигатора. `EventProcessor` и `event_prompt.py` готовы с Sprint 1, но не используются, потому что нет стратегии подачи данных.

**Подзадачи:**

| # | Подзадача | Описание |
|---|-----------|----------|
| 4.8.1 | Выбор архитектуры (см. варианты ниже) | Прототип + замер ресурсов на 5 URL → выбор варианта |
| 4.8.2 | `strategies/event_discovery.py` — стратегия обнаружения мероприятий | Crawl `/news`, `/afisha`, `/events`. Парсинг ленты: каждый анонс = `HarvestInput(entity_type=Event)`. Фильтры: свежесть (≤ 60 дней), маркеры мероприятий. Первая страница ленты (10-20 записей) |
| 4.8.3 | CLI: `--harvest-events` + Celery интеграция | CLI-флаг и таск/параметр для batch |
| 4.8.4 | Интеграция с Core API: `POST /api/internal/import/event` | Payload из `to_event_payload()`, привязка к организации |
| 4.8.5 | Пилотный тест: 10-20 сайтов (socinfo.ru КЦСОН) | Accuracy, ложные срабатывания, ресурсозатраты |

**Варианты архитектуры (решение — в Sprint 4 после прототипа):**

| Вариант | Суть | Плюсы | Минусы |
|---------|------|-------|--------|
| **A. Единый проход** | `multi_page.py` при обходе собирает ссылки из `/news` (уже видит их при discovery), но не включает в org-merge, а складывает в отдельный список. После OrganizationProcessor — этот список подаётся в EventProcessor. Один Playwright-сеанс на всё | Один crawl session, одна browser-сессия. Экономия ~30 с/URL на повторном запуске Playwright. `/news` markdown уже получен — не нужен re-crawl | Усложняет `multi_page.py` (два output). Больший memory footprint за сеанс. Event-обработка блокирует Organization-pipeline |
| **B. Двойной проход** | Сначала полный org-pipeline (как сейчас). Затем отдельный event-pipeline с собственным crawl `/news` | Простая архитектура: два независимых pipeline. Можно запускать event-pass реже или только для отдельных организаций | ×2 crawl-время и Playwright-сессий. Повторный запуск браузера для тех же сайтов |
| **C. Cached-hybrid** | При org-crawl в `multi_page.py` — markdown с `/news` уже скачивается (discovery их видит), но отбрасывается фильтром. Вместо отбрасывания — сохранять в кэш (файл/Redis). Event-pipeline потом читает из кэша без повторного crawl | Без повторного crawl. Event-pipeline легковесный (только LLM). Минимальный overhead в org-pipeline (+1 write в кэш) | Нужна инфраструктура кэширования. TTL/инвалидация. Markdown `/news` может устаревать |

**Рекомендация к исследованию:** начать с замера — сколько ссылок на мероприятия реально видит `multi_page.py` при discovery (они уже парсятся, но фильтруются). Если их достаточно — вариант C самый экономичный. Если нужна пагинация ленты и переход вглубь отдельных постов — вариант A или B.

**Инвариант (не зависит от варианта):** `/news` markdown НЕ включается в org-merge для OrganizationProcessor — это правильно, шум от новостей размывает classification организации. Мероприятия всегда обрабатываются отдельным `EventProcessor`.

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

> Обновлено: 2026-02-24 (Sprint 4)

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

### Спринт 2 — ЗАВЕРШЁН

> Обновлено: 2026-02-24. Отчёт: `harvester/docs/reports/2026-02-24__sprint2-classification-core-api.md`

| # | Задача | Статус | Заметки |
|---|--------|--------|---------|
| 2.1 | classifier.py | **Не нужен** | LLM-first: LLM классифицирует напрямую, post-hoc валидация в `_validate_codes()`. Отдельный модуль избыточен |
| 2.2 | `enrichment/dadata_client.py` — геокодирование | **Done** | Async httpx, clean/suggest API, graceful degradation без ключей, retry |
| 2.3 | confidence_scorer.py | **Не нужен** | AIConfidenceMetadata + decision routing в OrganizationProcessor покрывают полностью |
| 2.4 | payload_builder.py | **Не нужен** | `to_core_import_payload()` расширен поддержкой Dadata-enriched venues |
| 2.5 | `core_client/api.py` — HTTP-клиент к Core | **Done** | Mock mode без URL, retry, метрики. Полная State Machine в моке |
| 2.6 | E2E: URL → payload → POST в Core | **Done** | CLI: `--to-core` (Dadata + Core), `--enrich-geo` (только Dadata). Mock mode при отсутствии CORE_API_URL |
| 2.7 | Fixtures: HTML-снапшоты для тестов | **Done** | `kcson_vologda_markdown.txt`, `nko_obraz_zhizni_markdown.txt`, `expected_payload_kcson.json` |

**Дополнительно в Sprint 2:**

| Что | Файлы/детали |
|-----|-------------|
| Fix `target_audience` validation: `string` → `array` | `ImportController.php`: соответствие jsonb-колонке и array cast |
| 41 новый unit-тест (итого 76) | `test_dadata_client.py` (14), `test_core_client.py` (13), `test_payload_builder.py` (14) |
| `to_core_import_payload` с поддержкой geo | Venues обогащаются fias_id, geo_lat, geo_lon из Dadata |

**Архитектурные решения Sprint 2:**
- **Dadata suggest-first**: suggest API (бесплатный, 10K/день, растёт с подпиской) по умолчанию. Clean API (платный, higher accuracy) — opt-in через `DADATA_USE_CLEAN=true`.
- **Core client mock mode**: при пустом `CORE_API_URL` клиент валидирует payload локально и воспроизводит State Machine (accepted→approved/pending, needs_review→pending, rejected→rejected). Позволяет разрабатывать и тестировать без запущенного Core.
- **Graceful degradation**: каждый компонент (Dadata, Core) работает автономно. Отсутствие ключей не ломает пайплайн — просто пропускает обогащение.

### Спринт 3 — ЗАВЕРШЁН

> Обновлено: 2026-02-24. Отчёт: `harvester/docs/reports/2026-02-24__sprint3-multipage-celery.md`

| # | Задача | Статус | Заметки |
|---|--------|--------|---------|
| 3.1 | `strategies/multi_page.py` — multi-page crawl | **Done** | 17 паттернов подстраниц, discovery из markdown, priority scoring, merge ≤30K chars. Закрывает H1, H2 |
| 3.2 | Генерация CSS-шаблонов для КЦСОН | **Done** | `SocinfoExtractor` (markdown-based, 0 LLM-токенов). 10 полей, 31 тест, 8 реальных сайтов. CSS fragile из-за stripped classes — выбран markdown-подход |
| 3.3 | `strategies/css_strategy.py` — CSS-стратегия | **Done** | `CssTemplateRegistry`: load/has/get/build_extraction_config. Singleton + StrategyRouter-совместимый |
| 3.4 | Celery: `workers/celery_app.py`, `workers/tasks.py` | **Done** | crawl_and_enrich (single URL, retry 2x), process_batch (fan-out group). async через asyncio.run() |
| 3.5 | Docker: Dockerfile + docker-compose | **Done** | Multi-stage (worker/cli/test), redis:7-alpine, healthcheck, .dockerignore |
| 3.6 | Batch-тест: 50 организаций | **Done** | 50 URL из Core (12 КЦСОН, 8 мед., 8 socinfo, 7 НКО, 15 прочих). 45/50 успех, 25 accepted, 14 rejected, 6 needs_review. Cost: $0.0005/URL. 262 HTML-снимка сохранены |

**Дополнительно в Sprint 3:**

| Что | Файлы/детали |
|-----|-------------|
| CLI: `--multi-page`, `--site-extract` флаги | `run_single_url.py`: multi-page crawl + site extraction (0 LLM-токенов для socinfo.ru) |
| `strategies/site_extractors/` | `SiteExtractorRegistry` + `SocinfoExtractor`: auto-detect platform, extract 10 полей из markdown |
| 78 новых unit-тестов (итого 187) | `test_multi_page.py` (25), `test_css_strategy.py` (10), `test_celery_tasks.py` (12), `test_socinfo_extractor.py` (31) |

**Архитектурные решения Sprint 3:**
- **Multi-page merge**: каждая страница в отдельной секции с header (label + URL). Main page first, limit 30K total. Подстраницы приоритизированы: kontakty/rekvizity (100) > o-nas/uslugi (50) > struktura (25).
- **Celery + async**: `asyncio.run()` внутри sync-таска Celery. Один event loop на task, чистая изоляция. `worker_max_tasks_per_child=50` для предотвращения утечек Playwright.
- **Docker multi-stage**: единый Dockerfile, три target (worker, cli, test). docker-compose с healthcheck Redis и persistent volume.
- **Site Extractors vs CSS**: Crawl4AI `cleaned_html` теряет class/id → CSS-селекторы ненадёжны. Markdown от одной CMS стабилен → regex-based извлечение из markdown (SocinfoExtractor). Расширяемо: новая платформа = новый файл в `site_extractors/`.

### Спринт 4 — ЗАВЕРШЁН (инфраструктура), ОЖИДАЕТ (полный проход)

> Обновлено: 2026-02-24. Отчёт: `harvester/docs/reports/2026-02-24__sprint4-production-events.md`

| # | Задача | Статус | Заметки |
|---|--------|--------|---------|
| 4.1 | Structured logging (structlog) | **Done** | `config/logging.py`, JSON/console формат, все модули обновлены |
| 4.2 | Обработка ошибок, retry | **Done** | `enrichment/url_validator.py` — валидация URL до краула. Tenacity уже на месте в DeepSeek/Dadata/Core |
| 4.3 | Метрики (HarvestMetrics) | **Done** | `metrics/collector.py` — thread-safe, token cost, timing, confidence stats |
| 4.4 | Интеграция с Laravel | **Done** | `api/harvest_api.py` (FastAPI): POST /harvest/run, POST /harvest/events, GET /harvest/status |
| 4.5 | Firecrawl Cloud fallback | **Done** | `strategies/firecrawl_strategy.py`, интеграция в multi_page.py как fallback при неудаче Crawl4AI |
| 4.6 | Первый полный проход (~5 000 URL) | **Ожидает** | Инструментарий готов; нужны: Redis, ключ DeepSeek, Core API/mock, запуск |
| 4.7 | Анализ результатов, калибровка порогов | **Ожидает** | Зависит от 4.6 |
| 4.8 | Event harvesting | **Done** | `strategies/event_discovery.py` — 9 паттернов, keyword filter, freshness filter. CLI `--harvest-events`. Celery task `harvest_events` |

**Дополнительно в Sprint 4:**

| Что | Файлы/детали |
|-----|-------------|
| URL-валидация перед краулингом | `enrichment/url_validator.py`: предфильтр невалидных URL (закрывает 2/5 ошибок из Sprint 3.6) |
| 56 новых unit-тестов (итого 243) | `test_metrics_collector.py` (11), `test_url_validator.py` (14), `test_event_discovery.py` (14), `test_firecrawl_strategy.py` (7), `test_harvest_api.py` (6), `test_logging_config.py` (4) |
| FastAPI + uvicorn в dependencies | `pyproject.toml` обновлён |

**Архитектурные решения Sprint 4:**
- **Structlog everywhere**: единый формат логов (JSON для production, console для dev). Noisy loggers (crawl4ai, playwright, httpx) подавлены до WARNING.
- **Firecrawl как fallback, не замена**: Crawl4AI остаётся primary (бесплатный, no rate limit). Firecrawl подключается автоматически если main page не загрузилась И ключ есть.
- **Event harvesting: variant C (cached-hybrid)**: /news markdown НЕ включается в org-merge (правильно — шум размывает classification). EventDiscoverer отдельно crawlit /news, split по заголовкам, фильтрует по свежести и ключевым словам.
- **Harvest API**: FastAPI (не Django/Flask) — минимальный footprint, async-native, Pydantic-валидация. Celery dispatch, не синхронная обработка.

---

## 11. Бэклог: отложенные задачи и TODO

> Все задачи, выявленные в ходе разработки Sprint 1, тестирования и аудита.
> Приоритет: 🔴 критический, 🟡 важный, 🟢 желательный.

### 11.1. Python-пайплайн (ai-pipeline/harvester)

| # | Приоритет | Задача | Источник | Когда |
|---|-----------|--------|----------|-------|
| **H1** | ~~🟡~~ | ~~Multi-page стратегия: обход /kontakty, /o-nas, /uslugi, слияние markdown~~ | **Done.** `strategies/multi_page.py` — 17 паттернов, discovery, merge ≤30K | Sprint 3 ✅ |
| **H2** | ~~🟡~~ | ~~Title: на сайтах без явного юрлица LLM перефразирует название~~ | **Done.** Multi-page crawl подтягивает /o-nas, /svedeniya | Sprint 3 ✅ |
| **H3** | ~~🟡~~ | ~~Firecrawl fallback для SPA-сайтов~~ | **Done.** `strategies/firecrawl_strategy.py` + fallback в multi_page.py | Sprint 4 ✅ |
| **H4** | ~~🟢~~ | ~~`suggested_taxonomy` пустой во всех тестах~~ | **Done.** Добавлен Пример 5 (АНО «Образ жизни») с non-empty `suggested_taxonomy` | Sprint 5 ✅ |
| **H5** | ~~🟢~~ | ~~org_type_codes пустой для НКО/фондов~~ | **Done.** Исправлена подсказка «82 — НКО» → корректное разъяснение ownership_type vs org_type для НКО; Пример 5 (ownership="162", org_types=["142"]) | Sprint 5 ✅ |
| **H6** | ~~🟢~~ | ~~Переключить `prompt_registry.py` на новые промпты~~ | **Done.** Удалены 3 legacy-файла: `prompt_registry.py`, `base_system_prompt.py`, `strategy_router.py` — мёртвый код, ни один модуль их не импортировал | Sprint 5 ✅ |
| **H7** | ~~🟢~~ | ~~Интеграционный тест с реальным DeepSeek на 3-5 URL через `OrganizationProcessor.process()` с оценкой cache hit rate~~ | **Done.** `tests/test_integration_deepseek.py` — 5 тестов: КЦСОН accepted, детсад rejected, НКО accepted, cache hit rate > 0, schema compliance. Skip без API key | Sprint 5 ✅ |
| **H8** | ~~🟢~~ | ~~Расширить few-shot примеры: пример rejected-организации~~ | **Done.** Добавлен Пример 4 (Детский сад №15 — rejected, confidence=0.10) | Sprint 5 ✅ |
| **H9** | ~~🟡~~ | ~~Event harvesting: стратегия краулинга мероприятий + CLI + batch интеграция~~ | **Done.** `strategies/event_discovery.py`, CLI `--harvest-events`, Celery `harvest_events` task | Sprint 4 ✅ |
| **H10** | ~~🔴~~ | ~~Веб-поиск + обогащение org_website: модуль `search/`, исправление битых URL, поиск сайтов для организаций без source, обнаружение VK/OK/TG~~ | **Done.** 10 модулей в `search/`: `enrichment_pipeline.py` (tiered auto/review/reject), `url_fixer.py`, `source_discoverer.py`, `social_classifier.py`, `site_verifier.py`, `candidate_filter.py`, DuckDuckGo + Yandex providers. CLI `scripts/enrich_sources.py` (7 modes). Тесты: 6 test files | Sprint 5 ✅ |
| **H11** | ~~🟡~~ | ~~Интеграция SiteExtractor/CSS в harvest-шаг enrichment pipeline для экономии LLM-токенов~~ | **Done.** `run_single_url.py` проверяет `SiteExtractorRegistry.extract_if_known()` перед LLM. В `enrich_sources.py --fix-urls-verified` используется `EnrichmentPipeline` с полным harvest-шагом. Для socinfo.ru и аналогов — CSS-экстрактор (0 токенов) | Sprint 5 ✅ |

#### H11: Интеграция SiteExtractor/CSS в harvest-шаг enrichment pipeline ✅

Реализовано в двух точках:
1. **`run_single_url.py`** — `SiteExtractorRegistry.extract_if_known()` перед LLM. Флаг `--site-extract` для режима «только экстрактор, без LLM».
2. **`enrichment_pipeline.py`** — `_try_site_extractor()` в `_run_full_harvest()`: для socinfo.ru и аналогичных платформ SiteExtractor формирует condensed text (~1-2K символов) из извлечённых полей, который подаётся в `OrganizationProcessor` вместо полного markdown (~30K). Классификация сохраняется (LLM), но input на порядок меньше → быстрее + дешевле. Для нераспознанных платформ — fallback на полный markdown.

Вспомогательная функция `_build_condensed_text()` + 4 юнит-теста в `test_socinfo_extractor.py`.

**Оценка экономии:**
- На 2810 орг без источников: ~840 socinfo.ru × $0.004 = **~$3.36 экономии**
- При периодических обходах (5000 URL/месяц): ~$6/мес

| **H12** | 🟡 | Параллелизация auto_enrich: asyncio.Semaphore (3-5 воркеров) для ускорения обхода в ~3-4x. Альтернатива: перенос логики в Celery-задачу с concurrency. Ограничения: Playwright ~150 MB RAM/воркер, DeepSeek ~300 RPM, Yandex ~5-10 RPS | Sprint 5 run analysis | Sprint 6 |
| **H13** | 🟢 | Перенос auto_enrich в Celery-задачу для оркестрации через Laravel Scheduler. Позволит: автоматический запуск по расписанию, мониторинг через Flower, интеграция с Harvest API | Sprint 5 architecture | Sprint 6+ |
| **H14** | 🟢 | Дообогащение первых ~99 организаций текущего прогона (обработаны без import_organizer). Скрипт для повторного прохода по progress.jsonl с вызовом import для AUTO-записей без org_imported | Sprint 5 gap | Sprint 5 |
| **H18** | 🟡 | Регион/город в поиске и верификации: в ответе GET /organizations/without-sources при наличии отдавать регион (город); в enrich_missing_source передавать в discover_sources(..., city=...) и в Yandex Search API (regionId). Снижает долю REJECT из-за нерелевантной выдачи при одноимённых организациях | Прогон auto_enrich, кейс «Вызов» | Sprint 6 |
| **H19** | 🟡 | Верификатор: передавать регион/город в контекст LLM; по возможности верифицировать главную страницу (нормализованный корень URL), а не только первую попавшую подстраницу. Различать одноимённые организации (напр. «Вызов» Мурманск vs «Вызов» — премия за науку) | Кейс vyzov112.ru — ложное отрицание | Sprint 6 |
| **H20** | 🟢 | Кейс «Вызов» (БФ помощи «Вызов», Мурманск): поиск вернул корректный сайт vyzov112.ru, верификатор дал confidence=0.0 (ложное отрицание) из‑за отсутствия региона в контексте и приоритета подстраницы /about. Использовать при доработке H18–H19 | Case study 2026-02-26, reject разбор | Справочно |
| **H21** | 🟢 | **Проверки: тестовые/фейковые организации.** (1) Убедиться, что тестовые организации (Lookup Test Org, Rejected Test Org, Pending Review Test Org и т.п.) имеют статус не `approved`, чтобы не попадать в публичное API. (2) GET /api/internal/organizations/without-sources уже фильтрует по `status = approved` — краулер их не обходит. При необходимости: аудит БД или миграция, выставляющая явный статус (например `draft`/`rejected`) для записей с тестовыми названиями. | Прогон auto_enrich, тестовые org в результатах | Sprint 6 |

### 11.4. Политика и оркестрация сбора мероприятий (event harvest)

> Контекст: [ai-pipeline/harvester/docs/event-harvest-policy.md](../ai-pipeline/harvester/docs/event-harvest-policy.md) — когда запускать отдельный проход по мероприятиям; [event_ingestion_pipeline.md](../ai-pipeline/harvester/docs/event_ingestion_pipeline.md) — как обрабатываются мероприятия (универсальный пайплайн). Политика в коде уже есть: `harvest/event_harvest_policy.py` → `should_run_event_harvest_separately()`.

| # | Приоритет | Задача | Ссылка | Когда |
|---|-----------|--------|--------|-------|
| **H15** | 🟡 | **Оркестратор (Laravel / Scheduler):** при формировании очереди обхода для источников с `kind = org_website` по умолчанию **не** вызывать POST /harvest/events для того же URL после crawl_and_enrich; для источников-агрегаторов мероприятий (`event_aggregator`, `platform_silverage_events` и т.п.) — вызывать POST /harvest/events (или эквивалент). Использовать `should_run_event_harvest_separately(source_kind)` при наличии вызова из Laravel. | event-harvest-policy.md, § «Рекомендуемые шаги» п.2 | Sprint 6+ |
| **H16** | 🟢 | **События в том же проходе, что и организация:** в `run_organization_harvest` (или после него в tasks) расширить краул event-страницами или передавать в EventDiscoverer уже скачанный markdown; вызывать event ingestion pipeline, помечать, что для данного source события уже обработаны (чтобы оркестратор не ставил отдельный harvest_events). | event-harvest-policy.md, п.3; harvest-flows-a-b-c.md | Sprint 6+ |
| **H17** | 🟢 | **Core:** при появлении агрегаторов мероприятий ввести `kind` (например `event_aggregator`, `platform_silverage_events`) и в API due sources отдавать его, чтобы оркестратор различал «источник организации» и «источник мероприятий». | event-harvest-policy.md, п.4; Navigator_Core_Model_and_API | По мере появления агрегаторов |

### 11.2. Backend / Core API (Laravel)

| # | Приоритет | Задача | Источник | Когда |
|---|-----------|--------|----------|-------|
| **B1** | ~~🔴~~ | ~~Миграция: `source_reference` (string, indexed) в `organizations`, `events`~~ | **Done.** Миграция `2026_02_25_092349`, индексы на обеих таблицах. 14 тестов | Sprint 4 ✅ |
| **B2** | ~~🔴~~ | ~~Дедупликация организаций: fallback ключ `source_reference` → `inn` → `title`~~ | **Done.** `findExistingOrganization()`: source_reference → inn → create new. Тесты: dedup by source_ref, dedup by inn, separate without inn | Sprint 4 ✅ |
| **B3** | ~~🔴~~ | ~~Дедупликация событий: `updateOrCreate` по `(organizer_id, source_reference)`~~ | **Done.** `Event::updateOrCreate(['organizer_id', 'source_reference'], ...)`. Тест: повторный импорт обновляет, не дублирует | Sprint 4 ✅ |
| **B4** | ~~🟡~~ | ~~Миграция: `short_title` (varchar 100) в `organizations`~~ | **Done.** Миграция `2026_02_25_092353`, ImportController сохраняет. Тест: short_title persisted | Sprint 4 ✅ |
| **B5** | ~~🟡~~ | ~~Конвертация `vk_group_url` → `vk_group_id` при импорте~~ | **Done.** `extractVkGroupId()`: regex для club/public ID. Тест: vk_group_url converted | Sprint 4 ✅ |
| **B6** | ~~🟡~~ | ~~Auth middleware на internal API~~ | **Done.** Static Bearer Token: `AuthenticateInternalApi` middleware, `config/internal.php`, alias `auth.internal`. См. `backend/docs/internal_api_authentication.md` | Sprint 2 |
| **B7** | ~~🟡~~ | ~~`GET /api/internal/organizers?source_reference=X&inn=Y&source_id=Z` для lookup~~ | **Done.** `lookupOrganizer()`: fallback chain source_reference → inn → source_id. Тесты: lookup found, lookup 404 | Sprint 4 ✅ |
| **B8** | ~~🟢~~ | ~~Таблица `suggested_taxonomy_items` для модерации предложений от ИИ~~ | **Done.** Миграция `2026_02_25_093854`, модель `SuggestedTaxonomyItem` (UUID PK, organization_id FK, dictionary_type, suggested_name, ai_reasoning, status). `ImportController.storeSuggestedTaxonomy()` — `updateOrCreate` по (org_id, dictionary, term) | Sprint 5 ✅ |
| **B9** | ~~🟢~~ | ~~Dadata при импорте: вызывать `VenueAddressEnricher` в `processVenues()` автоматически~~ | **Resolved by B11.** Harvester Python-клиент `DadataClient` обогащает venues geo-данными ДО отправки в Core. `ImportController.resolveVenue()` принимает и сохраняет fias_id, fias_level, city_fias_id, region_iso, region_code, kladr_id. PHP VenueAddressEnricher остаётся для legacy WP-venues | Sprint 5 ✅ |
| **B10** | ~~🟢~~ | ~~Staging-таблицы для diff-анализа~~ | **Deferred → Phase 2.** Текущая архитектура (прямой import с dedup по source_reference/inn) достаточна для Sprint 5 / полного прохода. Staging-таблицы потребуются при внедрении модерации (diff-preview перед approve). Не блокирует текущую работу | Phase 2 |
| **B11** | ~~🟡~~ | ~~ImportController: принимать и сохранять `fias_level`, `city_fias_id`, `region_iso`, `region_code` в venues~~ | **Done.** `resolveVenue()`: сохраняет все geo-поля + kladr_id. Тест: venues receive geo fields | Sprint 4 ✅ |
| **B12** | ~~🟢~~ | ~~Консолидация Dadata: после B11 пересмотреть необходимость PHP `VenueAddressEnricher` для новых данных~~ | **Resolved.** Решение: PHP `VenueAddressEnricher` остаётся для: (1) legacy venues из WP, (2) reverse geocoding по координатам, (3) `organizations:enrich-from-dadata` artisan. Для новых импортов из Harvester — не нужен (Python Dadata обогащает до отправки). Artisan-команда не вызывается автоматически при импорте | Sprint 5 ✅ |

### 11.3. Обновлённые оценки ресурсов

По результатам Sprint 3.6 (batch-тест 50 URL, multi-page crawl):

| Ресурс | Прогноз (из §7) | Sprint 1.10 (5 URL) | Sprint 3.6 (50 URL) |
|--------|-----------------|---------------------|---------------------|
| DeepSeek API | $8–15 за 5 000 URL | ~$2.75 ($0.0006/URL) | **$2.51** ($0.0005/URL) |
| Cache hit rate | >90% | 75%+ | **100%** (batch mode) |
| Время на 1 URL | — | ~20s (single page) | **49s** (multi-page, 5 pages) |
| Crawl time | — | ~4s | **31s** (multi-page, avg 5 pages) |
| Classify time | — | ~16s | **17s** |
| Batch 50 URL (concurrency=2) | — | — | **19 мин** |
| Экстраполяция на 5 000 | ~28 ч | ~5 ч (6 workers) | **~8 ч** (6 workers, multi-page) |
| Success rate | — | 80% (4/5) | **90%** (45/50) |

**Sprint 4 дополнение:**
- Firecrawl fallback: ~$16/мес (Hobby plan), ожидается снижение error rate с 10% до ~5% (3 из 5 ошибок — невалидные URL, теперь фильтруются; 2 из 5 — недоступные сайты, покрываются Firecrawl)
- Event harvesting: дополнительно ~$0.0005/event (те же DeepSeek тарифы). При 5 event/сайт × 5000 сайтов ≈ $12.50 за полный event-проход
- Harvest API: ~0 дополнительных ресурсов (FastAPI + uvicorn — минимальный footprint)

---

## 12. Для агента: старт сессии

В начале сессии проверяю:
1. **Текущий спринт и задачу** — смотрю §10 (прогресс) и §11 (бэклог).
2. **Checkpoint** — был ли подтверждён предыдущий блок; если нет, сначала показываю результат и жду «ок» или правки.
3. **Нужно от тебя** — из блока спринта: ключи, контракт API, список URL, решение по мокам/Redis и т.д. Если чего-то не хватает, спрашиваю или делаю разумные моки и помечаю в коде/README.
4. **Спеки** — при неясностях смотрю Harvester_v1_Final Spec и Navigator_Core_Model_and_API; при расхождении предлагаю вариант и прошу утвердить.
5. **Бэклог** — проверяю §11 на отложенные задачи, которые пора взять в работу.
