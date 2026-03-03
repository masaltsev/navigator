# Агрегаторы: руководство по использованию

Спецификация и руководство по трём агрегаторным источникам данных Harvester: **ФПГ**, **СО НКО**, **Silver Age**.

- **Источник истины:** `docs/Navigator_Core_Model_and_API.md`
- **Архитектура AI Pipeline:** `docs/AI_Pipeline_Navigator_Plan.md`
- **Спецификация Harvester:** `docs/Harvester_v1_Final Spec.md`

---

## Содержание

1. [Общий обзор](#1-общий-обзор)
2. [Архитектура агрегаторов](#2-архитектура-агрегаторов)
3. [ФПГ — Фонд президентских грантов](#3-фпг--фонд-президентских-грантов)
4. [СО НКО — Реестр Минэкономразвития](#4-со-нко--реестр-минэкономразвития)
5. [Silver Age — silveragemap.ru](#5-silver-age--silveragemaprsu)
6. [Celery-задачи](#6-celery-задачи)
7. [Переменные окружения](#7-переменные-окружения)
8. [Расширение: добавление нового агрегатора](#8-расширение-добавление-нового-агрегатора)

---

## 1. Общий обзор

Агрегаторы — модули Harvester, которые обрабатывают **внешние реестры и каталоги** для пополнения базы организаций и мероприятий Navigator. В отличие от обхода сайтов конкретных организаций (`org_website`), агрегаторы работают с массивами данных из государственных и отраслевых реестров.

### Общий pipeline

Для организаций, о которых известны только **название и регион** (типично Silver Age; для ФПГ/СОНКО часто уже есть ИНН из реестра):

1. **Dadata** — один запрос `suggest_party(название, регион)` → сохраняем **весь ответ** (ИНН, ОГРН, адрес с геокодингом, контакты) и дальше по пайплайну используем его везде, без повторных вызовов: верификация по ИНН, подстановка в harvest/minimal-org, контакты и площадка из реестра.
2. **Сравнение с базой** — `lookup_organization(inn=…)` в Core API. Если организация уже есть в Core — идём по ветке «совпадение».
3. **Если организация уже в Core (matched):**
   - Запрашиваем привязанные источники: `list_sources(organizer_id, kind=org_website)` (в ответе есть `last_crawled_at`, `crawl_period_days`).
   - **Если источника типа org_website нет** — запускаем стратегию поиска источника (EnrichmentPipeline.enrich_missing_source / enrich_broken_url), при успехе создаём запись источника и при необходимости один раз краулим.
   - **Если источник org_website есть** — смотрим due date: если `last_crawled_at` не выставлен — краулим сайт, обновляем организацию из результата harvest, выставляем `last_crawled_at` у источника; если дата уже выставлена — ничего не делаем, источник попадёт в очередь по расписанию (/sources/due).
4. **Если организации нет в Core** — поиск источника (enrich_missing_source / enrich_broken_url) → при успехе harvest → import_organizer + создание source; иначе создание минимальной записи.
5. **В любом случае** (matched или created) — в описание организации добавляется контекст практики/агрегатора (например, описания практик Silver Age, проект ФПГ и т.д.).

Подробнее об унифицированном потоке и контексте — см. [раздел 2.4](#24-унифицированный-поток-enrichmentpipeline-и-контекст-агрегатора). **Мероприятия** из любых источников проходят через [универсальный пайплайн приёма мероприятий](event_ingestion_pipeline.md).

### Сравнительная таблица

| Характеристика | ФПГ | СО НКО | Silver Age |
|---|---|---|---|
| Источник данных | XLSX (28 МБ, 188K проектов) | XLSX (8.8 МБ, 111K записей) | Web scraping (1051 практика + 20 мероприятий) |
| URL источника | [президентскиегранты.рф](https://xn--80afcdbalict6afooklqi5o.xn--p1ai/public/open-data) | [data.economy.gov.ru](https://data.economy.gov.ru/analytics/sonko) | [silveragemap.ru](https://silveragemap.ru/poisk-proekta/) |
| Идентификатор организации | ИНН + ОГРН | ИНН + ОГРН | Название (ИНН отсутствует) |
| Фильтрация | Направление → Статус → Ключевые слова | ОКВЭД ∪ Ключевые слова | Не нужна (весь контент про пожилых) |
| Мероприятия | Нет | Нет | Да (20 мероприятий с `page_url`) |
| `source_kind` в Core | `registry_fpg` | `registry_sonko` | `platform_silverage` |
| Модуль | `aggregators/fpg/` | `aggregators/sonko/` | `aggregators/silverage/` |
| Зависимости | openpyxl | openpyxl | httpx, beautifulsoup4 |

---

## 2. Архитектура агрегаторов

### Структура модуля

Каждый агрегатор располагается в `aggregators/<name>/` и содержит:

```
aggregators/<name>/
├── __init__.py
├── models.py           # Pydantic-модели (Entry/Project, Organization)
├── xlsx_parser.py      # или scraper.py — источник данных
├── project_filter.py   # или org_filter.py — фильтрация (если нужна)
└── <name>_pipeline.py  # Оркестратор: весь pipeline от A до Z
```

CLI-скрипт: `scripts/run_<name>_import.py`
Celery-задача: `workers/tasks.py` → `process_<name>_batch`

**Следы запусков** — в одном месте: `data/runs/`. При передаче `--run-id <id>` (например `2026-02-27_silverage`) скрипты пишут в `data/runs/<run_id>/` те же артефакты, что и `auto_enrich`: `run_config.json`, `progress.jsonl` (по строке на организацию/событие), `run_summary.json`, плюс полный отчёт в `report.json`. Формат совместим с папкой запусков «организаций без источников».

### Общие зависимости

Все агрегаторы переиспользуют инфраструктуру Harvester:

| Компонент | Файл | Назначение |
|---|---|---|
| Core API клиент | `core_client/api.py` | `import_organizer()`, `import_event()`, `lookup_organization()` |
| Dadata | `enrichment/dadata_client.py` | Геокодирование, поиск реквизитов по ИНН |
| Поиск сайта | `search/source_discoverer.py` + `search/provider.py` | DuckDuckGo (по умолчанию) или Yandex Search API v2 (платный, по запросу) |
| Краулер | `strategies/multi_page.py` | Обход сайта организации (до 5 подстраниц) |
| LLM-классификатор | `processors/organization_processor.py` | DeepSeek классификация деятельности |
| Логирование | `config/logging.py` | structlog, `configure_logging()` |

### 2.3 Выбор поискового провайдера

Фабрика `search.provider.get_search_provider()` выбирает провайдер:

1. **DuckDuckGo** (по умолчанию) — бесплатный, подходит для большинства задач.
2. **Yandex Search API v2** (платный fallback, `~480 ₽ / 1000 запросов`) — качественнее для русскоязычных ресурсов. Включается явно: `SEARCH_PROVIDER=yandex` + `YANDEX_SEARCH_FOLDER_ID` + `YANDEX_SEARCH_API_KEY`.

Все три пайплайна (ФПГ, СОНКО, Silver Age) и `enrich_sources.py` используют эту фабрику.

> **Примечание:** файл провайдера Yandex называется `yandex_xml_provider.py` по историческим причинам. Внутри он использует Search API v2 (`searchapi.api.cloud.yandex.net/v2/web/searchAsync`), а не устаревший бесплатный Yandex.XML (закрыт с 2023).

### 2.4 Унифицированный поток: EnrichmentPipeline и контекст агрегатора

С февраля 2026 все три агрегатора используют **один и тот же** конвейер поиска и обогащения сайта — `search/enrichment_pipeline.py` (EnrichmentPipeline). Это устраняет дублирование логики и выравнивает поведение с основным сценарием «организации без источников» (см. `scripts/auto_enrich.py` и отчёт [2026-02-25__verified-enrichment-pipeline.md](reports/2026-02-25__verified-enrichment-pipeline.md)).

**Основные элементы:**

| Элемент | Назначение |
|--------|-------------|
| **EnrichmentPipeline.enrich_missing_source()** | Поиск кандидатов (discover_sources) → предфильтр и дедуп → верификация сайта (SiteVerifier) → при уверенности (tier AUTO) — полный harvest. Поддерживает опциональные `additional_context` и `source_kind`. |
| **additional_context** | Текстовый блок с данными агрегатора (практики, проекты, реестровые поля). Препендится к контенту сайта перед отправкой в LLM, чтобы классификация и описание учитывали и реестр, и страницу. |
| **source_kind** | Тег источника для HarvestInput и ai_source_trace: `registry_fpg`, `registry_sonko`, `platform_silverage`. |
| **_build_*_context(org)** | В каждом пайплайне — статический метод, формирующий `additional_context` из модели организации (Silver Age: практики и категории; ФПГ: проекты и направления; СОНКО: ОКВЭД, статусы, критерии). |
| **_update_matched_org()** | При совпадении организации в Core (lookup по ИНН/source_reference) вызывается обновление: в описание и ai_source_trace дописывается контекст агрегатора без создания дубликата. |

**Порядок шагов для одной организации:**

1. Lookup в Core (по ИНН и/или source_reference). Silver Age предварительно может получить ИНН через Dadata `suggest_party(name, region)`.
2. Если организация найдена — `_update_matched_org(existing, org, context)` и выход.
3. Иначе формируется контекст: `context = _build_*_context(org)`.
4. Вызов `EnrichmentPipeline.enrich_missing_source(..., additional_context=context, source_kind=...)`.
5. При успехе и наличии `harvest_output` — сборка payload (source_reference, inn/ogrn), `import_organizer`, `_create_source_record`.
6. Иначе — `_create_minimal_org(org)` (для Silver Age с опциональным ИНН и Dadata).

Подробный отчёт: [reports/2026-02-25__unified-enrichment-aggregators.md](reports/2026-02-25__unified-enrichment-aggregators.md).

### 2.5 Логика Dadata: общий пайплайн и кто вызывает

**Одна и та же логика Dadata** (suggest_party → ИНН для верификатора, контакты и площадка с геокодингом в payload) заложена в **общем пайплайне** `EnrichmentPipeline` и работает для **всех** флоу, которые вызывают `enrich_missing_source` / `enrich_broken_url`:

- **Организации без источников** (`scripts/auto_enrich.py`, Core API «without-sources»): вызов идёт в общий пайплайн без предзаполненных данных; **внутри пайплайна** один раз вызывается `_dadata_suggest(org_title, city)`, результат используется для верификатора (ИНН) и после harvest мержится в payload (`_merge_dadata_into_harvest`).
- **Одиночное обогащение** (`run_single_org_enrichment.py`): то же самое — пайплайн сам дергает Dadata один раз при вызове `enrich_*`.
- **ФПГ / СОНКО**: передают в пайплайн уже известный ИНН из реестра, но **не** передают `precomputed_dadata_party`; пайплайн при необходимости сам вызывает suggest (для контактов/площадки при мерже после harvest).
- **Silver Age (агрегатор)**: Dadata вызывается **до** входа в общий пайплайн — в `_process_organization` один раз делается `suggest_party(name, region)`, **весь ответ сохраняется** и передаётся в пайплайн как `precomputed_dadata_party`. Пайплайн при этом **не** вызывает Dadata повторно. Тот же сохранённый ответ используется в `_create_minimal_org` и в `_crawl_source_and_mark`, чтобы нигде не дублировать запросы.

Итого: логика «один ответ Dadata — везде переиспользовать» в общем пайплайне **есть для всех** (либо пайплайн сам делает один вызов, либо получает готовый `precomputed_dadata_party`). Подключаем мы Dadata **не до** вливания в общий пайплайн в смысле «отдельный путь» — мы вливаемся в тот же пайплайн; разница только в том, что в агрегаторе (Silver Age) первый вызов делается **до** входа в пайплайн, а результат передаётся в него и дальше переиспользуется во всех шагах (включая минимальную организацию и ре-краул источника).

---

## 3. ФПГ — Фонд президентских грантов

### 3.1 Описание

Каталог проектов, получивших (или не получивших) гранты ФПГ с 2017 года. Содержит 188 098 проектов с данными об организациях-заявителях, включая ИНН и ОГРН.

### 3.2 Файлы модуля

| Файл | Назначение |
|---|---|
| `aggregators/fpg/models.py` | `FPGProject` (строка XLSX), `FPGOrganization` (группа проектов одной организации) |
| `aggregators/fpg/xlsx_parser.py` | `download_xlsx()` — скачивание, `parse_xlsx()` — парсинг с валидацией заголовков |
| `aggregators/fpg/project_filter.py` | Четырёхступенчатая фильтрация: направление → статус → ключевые слова → дедупликация |
| `aggregators/fpg/card_scraper.py` | Дополнительный скрейпер карточек проектов (Crawl4AI, для детализации) |
| `aggregators/fpg/fpg_pipeline.py` | Оркестратор |
| `scripts/run_fpg_import.py` | CLI |

### 3.3 Фильтры

**Грантовые направления** (5 из ~12):
- Социальное обслуживание, социальная поддержка и защита граждан
- Охрана здоровья граждан, пропаганда здорового образа жизни
- Поддержка семьи, материнства, отцовства и детства
- Поддержка проектов в области культуры и искусства
- Поддержка проектов в области науки, образования, просвещения

**Исключения по статусу:**
- «Проект реализован неудовлетворительно»
- «Проект, к реализации которого победитель конкурса не приступал»

**Ключевые слова** (24 regex-паттерна): `пожил`, `старш`, `долголет`, `серебрян`, `пенсион`, `геронто`, `деменц`, `альцгейм`, `ветеран`, `55+`, `60+` и др.

Результат фильтрации: **~2 500 уникальных организаций** из 188K проектов.

### 3.4 CLI

```bash
# Скачивание XLSX
python -m scripts.run_fpg_import --download

# Анализ (статистика по фильтрам, без импорта)
python -m scripts.run_fpg_import --analyze --xlsx data/fpg/projects.xlsx

# Dry-run: показать, что будет импортировано (первые 20 организаций)
python -m scripts.run_fpg_import --xlsx data/fpg/projects.xlsx --limit 20 --dry-run

# Импорт с полным harvest
python -m scripts.run_fpg_import --xlsx data/fpg/projects.xlsx --limit 50

# Фильтр по направлению
python -m scripts.run_fpg_import --xlsx data/fpg/projects.xlsx \
  --direction "социальное обслуживание"

# Сохранение результатов в JSON
python -m scripts.run_fpg_import --xlsx data/fpg/projects.xlsx \
  --limit 10 --output data/fpg/results.json
```

**Аргументы:**

| Аргумент | Тип | Описание |
|---|---|---|
| `--xlsx` | str | Путь к XLSX (по умолчанию `data/fpg/projects.xlsx`) |
| `--download` | flag | Скачать XLSX перед обработкой |
| `--analyze` | flag | Только анализ (статистика по фильтрам) |
| `--dry-run` | flag | Показать без импорта в Core |
| `--limit` | int | Максимум организаций для обработки |
| `--direction` | str | Фильтр по конкретному направлению |
| `--output` / `-o` | str | Путь для сохранения JSON-результатов |

---

## 4. СО НКО — Реестр Минэкономразвития

### 4.1 Описание

Реестр социально ориентированных НКО Минэкономразвития РФ. Содержит 111 709 записей (51 473 уникальных ИНН) с данными организаций: ИНН, ОГРН, адрес, основной ОКВЭД.

### 4.2 Файлы модуля

| Файл | Назначение |
|---|---|
| `aggregators/sonko/models.py` | `SONKOEntry` (строка XLSX), `SONKOOrganization` (группа записей одного ИНН) |
| `aggregators/sonko/xlsx_parser.py` | `download_xlsx()` и `parse_xlsx()` — с обработкой специфической структуры файла (заголовки на 2-й строке, пустые строки в начале) |
| `aggregators/sonko/org_filter.py` | Фильтрация: ОКВЭД ∪ ключевые слова в названии → дедупликация по ИНН |
| `aggregators/sonko/sonko_pipeline.py` | Оркестратор |
| `scripts/run_sonko_import.py` | CLI |

### 4.3 Фильтры

**Основные ОКВЭД** (объединение — union):
- `87` — Деятельность по уходу с обеспечением проживания
- `88` — Предоставление социальных услуг без обеспечения проживания

**Расширенные ОКВЭД** (флаг `--broader-okved`):
- `86` — Здравоохранение
- `93` — Спорт, отдых, развлечения
- `96` — Прочие персональные услуги

**Ключевые слова** (18 regex-паттернов): `пожил`, `престарел`, `геронто`, `хоспис`, `паллиат`, `инвалид`, `маломоб`, `реабилит`, `дом.*престарел`, `интернат` и др.

Фильтр объединяет оба критерия (ОКВЭД **ИЛИ** ключевые слова) для охвата организаций, у которых ОКВЭД не указывает на социальные услуги, но название однозначно говорит о работе с пожилыми.

Результат: **~6 100 уникальных организаций** из 51K.

### 4.4 CLI

```bash
# Скачивание XLSX
python -m scripts.run_sonko_import --download

# Анализ (статистика по ОКВЭД и ключевым словам)
python -m scripts.run_sonko_import --analyze \
  --xlsx data/sonko/sonko_organizations.xlsx

# Dry-run
python -m scripts.run_sonko_import --xlsx data/sonko/sonko_organizations.xlsx \
  --limit 20 --dry-run

# С расширенными ОКВЭД
python -m scripts.run_sonko_import --xlsx data/sonko/sonko_organizations.xlsx \
  --broader-okved --analyze

# Полный импорт
python -m scripts.run_sonko_import --xlsx data/sonko/sonko_organizations.xlsx \
  --limit 50 --output data/sonko/results.json
```

**Аргументы:**

| Аргумент | Тип | Описание |
|---|---|---|
| `--xlsx` | str | Путь к XLSX (по умолчанию `data/sonko/sonko_organizations.xlsx`) |
| `--download` | flag | Скачать XLSX перед обработкой |
| `--analyze` | flag | Только анализ (статистика по фильтрам) |
| `--dry-run` | flag | Показать без импорта в Core |
| `--limit` | int | Максимум организаций |
| `--broader-okved` | flag | Включить расширенные ОКВЭД (86, 93, 96) |
| `--output` / `-o` | str | Путь для JSON-результатов |
| `--delay` | float | Задержка между организациями (по умолчанию 1.5 сек) |

---

## 5. Silver Age — silveragemap.ru

### 5.1 Описание

Сайт коалиции «Забота рядом» / альянса «Серебряный возраст». Два раздела:

1. **База практик** (`/poisk-proekta/`) — 1051 практика (65 страниц пагинации), каждая с отдельной детальной страницей. Практика содержит описание, регион, категории и блок с информацией об организации.
2. **Мероприятия** (`/meropriyatiya/`) — ~20 мероприятий (в основном онлайн-вебинары), каждое с детальной страницей.

**Ключевое отличие:** все материалы на сайте посвящены работе с пожилыми людьми — фильтрация по релевантности не нужна. ИНН/ОГРН на сайте отсутствуют — сопоставление организаций только по названию.

### 5.2 Файлы модуля

| Файл | Назначение |
|---|---|
| `aggregators/silverage/models.py` | `SilverAgePractice`, `SilverAgeEvent`, `SilverAgeOrganization` |
| `aggregators/silverage/scraper.py` | Web scraper (httpx + BeautifulSoup): пагинация, парсинг деталей, кэширование |
| `aggregators/silverage/silverage_pipeline.py` | Оркестратор: scrape → group → process orgs → events |
| `scripts/run_silverage_import.py` | CLI |

### 5.3 Данные, извлекаемые из практик

Со страницы каждой практики (`/poisk-proekta/{slug}/`) извлекаются:

| Поле | Источник в HTML |
|---|---|
| Название практики | `.titlePage` или `<h1>` |
| Регион | `.region` внутри `.region_info` |
| Даты | `.data` внутри `.region_info` |
| Категории | CSS-классы `.icon_project.backcolor_*` (только первый контейнер) |
| Полное описание | `.content` (после удаления `.region_info` и `.icon_project_container`) |
| **Организация — имя** | `#info_popup` (текстовый блок, первое предложение) |
| **Организация — описание** | `#info_popup` (полный текст) |
| **Организация — email** | `#info_popup` (regex `\w+@\w+\.\w+`) |
| **Организация — телефон** | `#info_popup` (regex `\+?\d[\d\s()-]+`) |
| **Организация — VK** | `#info_popup` (URL с `vk.com`) |
| **Организация — сайт** | `#info_popup` (URL, исключая соцсети: vk.com, ok.ru, max.ru, t.me, youtube, rutube) |

### 5.4 Данные, извлекаемые из мероприятий

Со страницы каждого мероприятия (`/meropriyatiya/{slug}/`):

| Поле | Источник в HTML |
|---|---|
| Название | `.titlePage` |
| Категория | `.newsTag` |
| Описание | `.containerProject-content` |
| Место проведения | Текст после «Место проведения» в `.region_info` |
| Дата/время | Текст после «Сроки проведения» в `.region_info` |
| Ссылка на регистрацию | `<a href>` с доменами timepad.ru, nethouse.ru, ticketscloud |
| URL страницы мероприятия | Формируется автоматически из slug |

### 5.5 Группировка по организациям

Практики группируются по имени организации (case-insensitive). Результат — `SilverAgeOrganization` со свойствами:

- `practice_count` — количество практик
- `all_categories` — объединение категорий из всех практик
- `best_description` — самое длинное описание (из org info или описания практики)
- `source_reference` — `silverage_org_{slug_from_name}`

Организации сортируются по количеству практик (убывание).

### 5.6 Кэширование

Скрейпер поддерживает кэширование скрейпленных страниц в JSON-файлы:

```
data/silverage/cache/
├── practice/
│   ├── kulinarnaya-studiya-vkus-zhizni.json
│   ├── vtoroe-dykhanie.json
│   └── ...
└── event/
    ├── podvedenie-itogov-aktsii-priznanie-2025.json
    └── ...
```

При повторном запуске скрейпер загружает данные из кэша, не делая HTTP-запросов. Это полезно при отладке и повторных прогонах.

### 5.7 CLI

```bash
# Анализ: скрейпить первые 3 страницы практик, показать статистику
python -m scripts.run_silverage_import --analyze --max-pages 3 \
  --cache-dir data/silverage/cache

# Dry-run: 5 практик + мероприятия
python -m scripts.run_silverage_import --max-practices 5 --dry-run

# Импорт первых 10 организаций (без мероприятий)
python -m scripts.run_silverage_import --max-practices 20 \
  --limit-orgs 10 --no-events

# Полный импорт с кэшированием и сохранением результатов
python -m scripts.run_silverage_import \
  --cache-dir data/silverage/cache \
  --output data/silverage/results.json

# Ускоренный скрейпинг (0.8 сек между запросами)
python -m scripts.run_silverage_import --analyze --max-pages 2 \
  --scrape-delay 0.8
```

**Аргументы:**

| Аргумент | Тип | Описание |
|---|---|---|
| `--analyze` | flag | Только скрейпинг + статистика (без импорта) |
| `--dry-run` | flag | Показать без импорта в Core |
| `--max-pages` | int | Максимум страниц пагинации практик (каждая ~9-16 практик, всего 65) |
| `--max-practices` | int | Максимум детальных страниц практик для скрейпинга |
| `--limit-orgs` | int | Максимум организаций для обработки (после группировки) |
| `--no-events` | flag | Пропустить скрейпинг мероприятий |
| `--cache-dir` | str | Директория для кэша скрейпленных страниц |
| `--output` / `-o` | str | Путь для JSON-результатов |
| `--scrape-delay` | float | Задержка между HTTP-запросами (по умолчанию 1.5 сек) |

### 5.8 Оценка времени

| Операция | Объём | Оценка времени (delay=1.5s) |
|---|---|---|
| Скрейпинг списка практик | 65 страниц | ~2 мин |
| Скрейпинг деталей практик | 1051 страница | ~26 мин |
| Скрейпинг мероприятий | 20 страниц | ~30 сек |
| Обработка организаций | зависит от `--limit-orgs` | ~2-5 сек/орг (без harvest) |
| **Полный прогон (scrape + group)** | — | **~30 мин** |

---

## 6. Celery-задачи

Все агрегаторы зарегистрированы как Celery-задачи в `workers/tasks.py`.

### 6.1 Задачи

| Задача | Имя | Описание |
|---|---|---|
| ФПГ | `workers.tasks.process_fpg_batch` | Парсинг XLSX → фильтрация → match_or_create |
| СО НКО | `workers.tasks.process_sonko_batch` | Парсинг XLSX → фильтрация → match_or_create |
| Silver Age | `workers.tasks.process_silverage_batch` | Скрейпинг → группировка → match_or_create + events |

### 6.2 Вызов через Celery

```python
from workers.tasks import process_fpg_batch, process_sonko_batch, process_silverage_batch

# ФПГ
result = process_fpg_batch.delay(
    xlsx_path="data/fpg/projects.xlsx",
    limit=50,
    dry_run=False,
)

# СО НКО
result = process_sonko_batch.delay(
    xlsx_path="data/sonko/sonko_organizations.xlsx",
    limit=50,
    dry_run=False,
    include_broader_okved=False,
)

# Silver Age
result = process_silverage_batch.delay(
    max_pages=5,
    max_practices=50,
    limit_orgs=20,
    dry_run=False,
    scrape_events=True,
    cache_dir="data/silverage/cache",
)
```

### 6.3 Запуск worker

```bash
cd ai-pipeline/harvester
celery -A workers.celery_app worker --loglevel=info --concurrency=2
```

---

## 7. Переменные окружения

Все агрегаторы используют общие переменные из `.env`:

| Переменная | Обязательна | Описание |
|---|---|---|
| `CORE_API_URL` | Да (для реального импорта) | URL Core API Laravel (`http://localhost:8000`) |
| `CORE_API_TOKEN` | Да (для реального импорта) | Bearer-токен для Core API |
| `DEEPSEEK_API_KEY` | Да (для harvest) | API ключ DeepSeek (LLM-классификация) |
| `DADATA_API_KEY` | Нет | API ключ Dadata (геокодирование, поиск по ИНН) |
| `DADATA_SECRET_KEY` | Нет | Secret ключ Dadata |
| `CELERY_BROKER_URL` | Для Celery | URL Redis (`redis://localhost:6379/0`) |

Если `CORE_API_URL` не задан, Core-клиент работает в mock-режиме (все вызовы возвращают `None`), что удобно для `--analyze` и `--dry-run`.

---

## 8. Расширение: добавление нового агрегатора

### 8.1 Чек-лист

1. **Создать директорию** `aggregators/<name>/` с `__init__.py`

2. **Определить модели** (`models.py`):
   - Entry/Project — одна запись из источника
   - Organization — агрегация записей по ИНН или названию
   - Для каждой модели — `source_reference` (property, уникальный идентификатор для Core API)

3. **Создать парсер/скрейпер**:
   - Для XLSX: `xlsx_parser.py` с `download_xlsx()` и `parse_xlsx()`
   - Для веб-источника: `scraper.py` с httpx + BeautifulSoup

4. **Создать фильтр** (если нужен) — `*_filter.py`:
   - Определить критерии фильтрации (ОКВЭД, ключевые слова, направления)
   - Реализовать `run_filter_pipeline()` с `FilterStats`

5. **Создать pipeline** (`<name>_pipeline.py`):
   - Переиспользовать `NavigatorCoreClient`, `DadataClient` и **EnrichmentPipeline** (`search/enrichment_pipeline.py`) для поиска сайта и полного harvest.
   - Реализовать статический метод **`_build_<name>_context(org)`** — текстовый блок с данными агрегатора для передачи в `enrich_missing_source(..., additional_context=..., source_kind=...)`.
   - При совпадении организации в Core вызывать **`_update_matched_org(existing, org, context)`** для обогащения описания и ai_source_trace.
   - Реализовать `run()` с поддержкой `dry_run`, `limit`, `output_path`.
   - Определить `PipelineReport` dataclass с `summary()` и `to_dict()`.

6. **Создать CLI** (`scripts/run_<name>_import.py`):
   - Базовые флаги: `--analyze`, `--dry-run`, `--limit`, `--output`
   - Специфичные для источника флаги

7. **Добавить Celery-задачу** в `workers/tasks.py`:
   - `@app.task(bind=True, name="workers.tasks.process_<name>_batch", max_retries=0, acks_late=True)`

8. **Обновить зависимости** в `pyproject.toml` (если нужны новые библиотеки)

9. **Написать тесты** в `tests/test_<name>_*.py`:
   - Парсинг фикстур (HTML / XLSX mock)
   - Фильтрация
   - Группировка / дедупликация
   - Pipeline dry-run (mock Core client)
   - Обработка ошибок

### 8.2 Именование `source_kind`

Используется в `ai_source_trace` Core API для идентификации источника:

| Тип | Паттерн | Пример |
|---|---|---|
| Государственный реестр | `registry_<short_name>` | `registry_fpg`, `registry_sonko` |
| Отраслевая платформа | `platform_<short_name>` | `platform_silverage` |
| Сайт организации | `org_website` | `org_website` |

### 8.3 Именование `source_reference`

Уникальный идентификатор записи в Core API для дедупликации:

| Агрегатор | Паттерн | Пример |
|---|---|---|
| ФПГ | `fpg_inn_{inn}` | `fpg_inn_7710515050` |
| СО НКО | `sonko_inn_{inn}` | `sonko_inn_5263012345` |
| Silver Age (org) | `silverage_org_{slug}` | `silverage_org_огбу_«октябрьский_геронтоло` |
| Silver Age (practice) | `silverage_practice_{slug}` | `silverage_practice_kulinarnaya-studiya-vkus-zhizni` |
| Silver Age (event) | `silverage_event_{slug}` | `silverage_event_podvedenie-itogov-2025` |

---

## Тестирование

Все агрегаторы покрыты unit-тестами:

```bash
# Все тесты агрегаторов
python -m pytest tests/test_fpg_*.py tests/test_sonko_*.py tests/test_silverage_*.py -v

# Все тесты проекта
python -m pytest tests/ -v --ignore=tests/test_integration_deepseek.py --ignore=tests/test_harvest_api.py
```

| Модуль | Кол-во тестов | Покрытие |
|---|---|---|
| ФПГ | ~27 | Парсер, фильтры, pipeline, context builder, matched-org update |
| СО НКО | ~24 | Парсер, фильтры, pipeline, context builder, matched-org update |
| Silver Age | 37 | Scraper (list + detail), org info, events, pipeline, grouping, context builder, matched-org update |
| **Итого** | **~88** | — |

**См. также:**
- [harvest-flows-a-b-c.md](harvest-flows-a-b-c.md) — потоки обогащения организаций (кейсы А–В) и место мероприятий в схеме.
- [event-harvest-policy.md](event-harvest-policy.md) — когда запускать отдельный сбор мероприятий.
- [event_ingestion_pipeline.md](event_ingestion_pipeline.md) — универсальный пайплайн приёма мероприятий.
- Отчёт [2026-02-25__unified-enrichment-aggregators.md](reports/2026-02-25__unified-enrichment-aggregators.md) — унификация потока обогащения и контекстные билдеры.
