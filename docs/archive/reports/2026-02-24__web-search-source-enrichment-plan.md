# План: Веб-поиск и обогащение org_website источников

> **Дата:** 2026-02-24  
> **Область:** `ai-pipeline/harvester/`, `backend/` (Core API)  
> **Источник истины:** `docs/Navigator_Core_Model_and_API.md`, `docs/Harvester_v1_Final Spec.md`, `docs/Harvester_v1_Development_Plan.md`  
> **Контекст:** Harvester v1 Sprints 1–4 завершены. Инфраструктура для полного прохода org_website готова, но база содержит организации с невалидными или отсутствующими источниками.

---

## 1. Проблема

В таблице `organizations` находится ~5 000 записей. Для промышленного обхода Harvester'ом каждая организация должна иметь хотя бы один валидный `source` типа `org_website`. Аудит Sprint 3.6 показал:

| Категория | Описание | Пример из batch-теста |
|-----------|----------|-----------------------|
| **A. Битый URL** | Источник `org_website` существует, но URL невалиден: обрезан домен, отсутствует TLD, DNS не резолвится, сайт мигрировал | `mikh-kcson.ryazan.` (обрезанный домен), `kcson23.uszn032.ru` (DNS failure) |
| **B. Нет источника** | У организации вообще нет `source` с `kind=org_website` | Организации, импортированные из WP без сайта |
| **C. Соцсети как альтернатива** | У организации есть активные страницы в ВК/ОК/Telegram, но они не заведены как source | Группы ВК серебряных волонтёров, ОК-страницы КЦСОН |

**Масштаб оценки:** по итогам Sprint 3.6, 10% ошибок (5 из 50) вызваны проблемами с URL. Экстраполяция на 5 000 URL: ~500 организаций с невалидными источниками. Количество организаций без `org_website` — требует SQL-аудит, но оценочно 10–30%.

---

## 2. Цель

1. **Реализовать универсальный модуль веб-поиска** (`search/`) в Harvester — переиспользуемый компонент для поиска информации в интернете от имени агента.
2. **Применить его для обогащения базы источников**: исправить битые URL, найти сайты для организаций без `org_website`, обнаружить страницы в соцсетях.
3. **Расширить типологию источников**: заводить VK/OK/Telegram-страницы как отдельные `source` с соответствующим `kind`.

---

## 3. Веб-поиск: выбор API и архитектура

### 3.1. Сравнение поисковых API

| API | Качество по RU | Free tier | Стоимость | API key | Примечание |
|-----|---------------|-----------|-----------|---------|------------|
| **Yandex Search API** (Yandex Cloud) | Отличное | 1 000 запросов/мес | ~$15/мес за 10K запросов | Да (OAuth + folder_id) | Лучшее покрытие .ru, социальных сетей, госсайтов. Python-клиент `yandex-search-api` |
| **SerpAPI** | Хорошее (Yandex engine) | 100 запросов/мес | $50/мес за 5 000 | Да | Абстракция поверх Yandex/Google. Удобно, дороже |
| **DuckDuckGo** (`duckduckgo-search`) | Среднее | Безлимит* | $0 | Нет | Бесплатно, нет API key. Rate-limiting при большом объёме. Качество для .ru ниже |

\* DuckDuckGo — неофициальный scraping-метод, возможен rate-limit при >100 запросов/час.

### 3.2. Рекомендация

**Двухуровневая стратегия:**

1. **Разработка и тестирование (MVP):** `duckduckgo-search` — ноль затрат, не требует API-ключей, достаточно для проверки алгоритмов на 50–100 организациях.
2. **Продакшен:** Yandex Search API (Yandex Cloud) — лучшее качество для российского сегмента. Стоимость для полного прогона 5 000 организаций: ~$10–15. Аккаунт Yandex Cloud с юрлицом уже есть.

Клиентский код абстрагируется через интерфейс `WebSearchProvider`, чтобы переключение между движками не требовало изменения логики обогащения.

### 3.3. Архитектура модуля

```
ai-pipeline/harvester/
├── search/
│   ├── __init__.py
│   ├── provider.py              # ABC WebSearchProvider + SearchResult dataclass
│   ├── duckduckgo_provider.py   # DuckDuckGo (MVP, 0 cost)
│   ├── yandex_provider.py       # Yandex Search API (production)
│   ├── url_fixer.py             # Логика исправления битых URL
│   └── source_discoverer.py     # Обнаружение сайтов и соцсетей для организаций
```

### 3.4. Ключевые абстракции

```python
# search/provider.py
from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    position: int

class WebSearchProvider(ABC):
    @abstractmethod
    async def search(self, query: str, num_results: int = 10) -> list[SearchResult]:
        """Выполнить поиск и вернуть результаты."""
        ...

    @abstractmethod
    async def search_site(self, query: str, domain_hint: str, num_results: int = 5) -> list[SearchResult]:
        """Поиск с привязкой к домену (site: или inurl:)."""
        ...
```

---

## 4. Сценарии обогащения

### 4.1. Сценарий A — Исправление битых URL

**Вход:** организация с `source.kind=org_website`, но URL невалиден или недоступен.

**Алгоритм:**

```
1. url_validator.validate_url(source.base_url)
   → is_valid=False, reason="truncated_tld" / "missing_scheme" / ...

2. Извлечь фрагмент домена:
   "mikh-kcson.ryazan." → "mikh-kcson ryazan"
   "kcson23.uszn032.ru" → "kcson23 uszn032"

3. Поиск по фрагменту:
   query = f'"{domain_fragment}" сайт'
   results = web_search.search(query, num_results=5)

4. Для каждого результата:
   a. Проверить: url_validator.validate_url(result.url)
   b. Проверить: domain содержит ключевые части фрагмента
   c. Пробный HTTP HEAD → 200 OK?
   d. Если ок → кандидат на замену

5. Если кандидатов >1, ранжировать:
   - Совпадение домена с фрагментом (>80% → score +50)
   - Наличие ключевых слов организации в title/snippet (+30)
   - HTTPS предпочтительнее HTTP (+10)
   - .ru/.рф домен (+10)

6. Лучший кандидат → обновить source.base_url
   (или предложить на модерацию, если confidence < порога)
```

### 4.2. Сценарий B — Поиск сайта для организации без источника

**Вход:** организация без `source.kind=org_website`.

**Алгоритм:**

```
1. Сформировать поисковый запрос:
   title = organization.title          # "КЦСОН Пролетарского района"
   city  = organization.venues[0].city # "Ростов-на-Дону" (из Dadata/venue)
   query = f'"{title}" {city} официальный сайт'

2. web_search.search(query, num_results=10)

3. Классифицировать каждый результат:
   ┌─ Официальный сайт (.ru, .gov.ru, .рф, содержит ключевые слова org)
   ├─ ВКонтакте (vk.com/...)
   ├─ Одноклассники (ok.ru/...)
   ├─ Telegram (t.me/...)
   └─ Прочее (агрегаторы, каталоги — игнорировать)

4. Для official_website:
   a. HEAD-проверка доступности
   b. Быстрый crawl → есть ли название организации / ИНН в тексте
   c. Если match → создать source(kind=org_website, base_url=url)

5. Для VK/OK/TG: → Сценарий C
```

### 4.3. Сценарий C — Обнаружение и заведение соцсетей

**Вход:** URL формата `vk.com/...`, `ok.ru/...`, `t.me/...`, найденный при поиске или при краулинге сайта организации.

**Маппинг на модель Core:**

| Найденный URL | `source.kind` | Доп. поле в `organizations` |
|---------------|---------------|----------------------------|
| `vk.com/club12345` или `vk.com/kcson_vologda` | `vk_group` | `vk_group_id` (integer) |
| `ok.ru/group/54321` | `ok_group` | `ok_group_id` (integer) |
| `t.me/kcson_channel` | `tg_channel` | — (новое поле или через source) |

**Алгоритм:**

```
1. Распознать тип соцсети по URL:
   - vk.com/club{id} | vk.com/{slug} → kind=vk_group
   - ok.ru/group/{id} | ok.ru/profile/{id} → kind=ok_group  
   - t.me/{slug} → kind=tg_channel

2. Извлечь ID/slug:
   - VK: resolve screen_name через VK API или HTML-парсинг → group_id
   - OK: group_id из URL
   - TG: username из URL

3. Проверить дубликат:
   - Есть ли уже source с этим base_url для данной организации?

4. Создать source в Core:
   POST /api/internal/sources/create
   {
     "organizer_id": "<uuid>",
     "kind": "vk_group",
     "base_url": "https://vk.com/kcson_vologda",
     "name": "ВК: КЦСОН Вологда",
     "is_active": true,
     "crawl_period_days": 7
   }

5. Обновить organizations:
   - vk_group_id = <extracted_id>  (если VK)
   - ok_group_id = <extracted_id>  (если OK)
```

**Бонус при краулинге org_website:** при обходе официального сайта организации Harvester уже видит ссылки на соцсети (footer/header). Сейчас `SocinfoExtractor` извлекает `vk_url` / `ok_url`. Расширить логику: автоматически заводить source для найденных соцсетей.

---

## 5. Интеграция с Core API

### 5.1. Новые / расширенные endpoints (Laravel)

| Endpoint | Метод | Назначение | Статус |
|----------|-------|-----------|--------|
| `GET /api/internal/sources?kind=org_website&status=error` | GET | Выборка источников с битыми URL | Частично есть (source_loader) |
| `GET /api/internal/organizers/without-source?kind=org_website` | GET | Организации без org_website | **Новый** |
| `PATCH /api/internal/sources/{id}` | PATCH | Обновить base_url у существующего source | **Новый** (B7 из бэклога) |
| `POST /api/internal/sources` | POST | Создать новый source и привязать к organizer | **Новый** |
| `PATCH /api/internal/organizations/{id}` | PATCH | Обновить vk_group_id / ok_group_id | **Новый** |

### 5.2. SQL-аудит перед стартом

```sql
-- Организации с невалидными org_website
SELECT o.id, o.title, s.base_url, s.last_status
FROM organizations o
JOIN organizers org ON org.organizable_id = o.id AND org.organizable_type = 'Organization'
JOIN sources s ON s.organizer_id = org.id AND s.kind = 'org_website'
WHERE s.last_status IN ('error', 'pending')
   OR s.base_url !~ '^https?://[a-zA-Z0-9].*\.[a-zA-Z]{2,}';

-- Организации вообще без org_website
SELECT o.id, o.title, 
       (SELECT city FROM venues v 
        JOIN organization_venues ov ON ov.venue_id = v.id 
        WHERE ov.organization_id = o.id LIMIT 1) as city
FROM organizations o
JOIN organizers org ON org.organizable_id = o.id AND org.organizable_type = 'Organization'
WHERE NOT EXISTS (
    SELECT 1 FROM sources s 
    WHERE s.organizer_id = org.id AND s.kind = 'org_website'
);
```

---

## 6. CLI и Celery-интеграция

### 6.1. CLI

```bash
# Аудит: показать статистику по источникам
python -m scripts.source_audit --stats

# Исправить битые URL (сценарий A) для 10 организаций (dry-run)
python -m scripts.enrich_sources --fix-urls --limit 10 --dry-run

# Найти сайты для организаций без источника (сценарий B)
python -m scripts.enrich_sources --find-missing --limit 10 --dry-run

# Полный прогон с записью в Core
python -m scripts.enrich_sources --fix-urls --find-missing --send-to-core

# Поиск сайта для одной организации
python -m scripts.enrich_sources --org-title "КЦСОН Вологды" --city "Вологда"
```

### 6.2. Celery tasks

```python
# workers/tasks.py (расширение)

@app.task(bind=True, max_retries=2, default_retry_delay=60)
def fix_source_url(self, source_data: dict):
    """Сценарий A: найти и исправить битый URL для одного source."""
    ...

@app.task(bind=True, max_retries=2)
def discover_source(self, org_data: dict):
    """Сценарий B+C: найти сайт и соцсети для организации."""
    ...

@app.task
def enrich_sources_batch(org_ids: list[str], fix_urls=True, find_missing=True):
    """Fan-out: обогащение пачки организаций."""
    ...
```

### 6.3. Harvest API (FastAPI — расширение)

| Endpoint | Метод | Назначение |
|----------|-------|-----------|
| `POST /harvest/enrich-sources` | POST | Dispatch поиска источников для списка организаций |
| `GET /harvest/source-audit` | GET | Возвращает статистику: сколько битых URL, сколько без source |

---

## 7. Пошаговый план внедрения

### Sprint 5a (3–4 дня): Web Search + URL Fix

| # | Задача | Файлы | Часы |
|---|--------|-------|------|
| 5a.1 | `search/provider.py` — ABC `WebSearchProvider`, dataclass `SearchResult` | `search/` | 1 |
| 5a.2 | `search/duckduckgo_provider.py` — реализация через `duckduckgo-search` (MVP, 0 cost) | `search/` | 2 |
| 5a.3 | `search/yandex_provider.py` — реализация через `yandex-search-api` (production) | `search/` | 3 |
| 5a.4 | `search/url_fixer.py` — логика извлечения фрагмента домена, поиск, ранжирование кандидатов, HEAD-проверка | `search/` | 4 |
| 5a.5 | Юнит-тесты для search-модуля (мокированные результаты, без сети) | `tests/test_search*.py` | 3 |
| 5a.6 | CLI: `scripts/enrich_sources.py --fix-urls` (dry-run + send-to-core) | `scripts/` | 2 |
| 5a.7 | Тест на 10–20 организациях с битыми URL | — | 2 |

**DoD:** CLI принимает организации с битыми URL → ищет через DuckDuckGo → выводит кандидатов.  
**От тебя:** SQL-аудит или экспорт организаций с невалидными URL из Core.

### Sprint 5b (3–4 дня): Source Discovery + Social Media

| # | Задача | Файлы | Часы |
|---|--------|-------|------|
| 5b.1 | `search/source_discoverer.py` — формирование запроса, классификация результатов (official / VK / OK / TG / ignore), HEAD-проверка | `search/` | 4 |
| 5b.2 | `search/social_classifier.py` — распознавание и парсинг URL соцсетей, извлечение group_id | `search/` | 3 |
| 5b.3 | Расширение `core_client/api.py` — методы для PATCH source, POST source, PATCH organization (vk_group_id, ok_group_id) | `core_client/` | 3 |
| 5b.4 | CLI: `scripts/enrich_sources.py --find-missing` + `--discover-social` | `scripts/` | 2 |
| 5b.5 | Юнит-тесты для source_discoverer и social_classifier | `tests/` | 3 |
| 5b.6 | Тест на 20–30 организациях без источников | — | 2 |

**DoD:** CLI для организации без сайта → находит официальный сайт и/или ВК/ОК/ТГ → выводит результат.  
**От тебя:** (1) Список организаций без org_website (SQL или API); (2) Решение по новым endpoints в Core (PATCH source, POST source).

### Sprint 5c (2–3 дня): Celery-интеграция + продакшен прогон

| # | Задача | Файлы | Часы |
|---|--------|-------|------|
| 5c.1 | Celery tasks: `fix_source_url`, `discover_source`, `enrich_sources_batch` | `workers/tasks.py` | 3 |
| 5c.2 | FastAPI: `POST /harvest/enrich-sources`, `GET /harvest/source-audit` | `api/harvest_api.py` | 2 |
| 5c.3 | Переключение на Yandex Search API (если MVP на DuckDuckGo подтвердил алгоритмы) | `search/yandex_provider.py` | 2 |
| 5c.4 | Rate-limiting: задержка между поисковыми запросами (1–2 сек для DuckDuckGo, по лимитам для Yandex) | `search/` | 1 |
| 5c.5 | Продакшен прогон: исправление URL (категория A) + поиск сайтов (категория B) для всей базы | — | 4 |
| 5c.6 | Отчёт по результатам обогащения | `docs/reports/` | 2 |

**DoD:** Все организации проверены; битые URL исправлены или помечены; организации без сайтов обогащены найденными URL и соцсетями.  
**От тебя:** (1) Ключ Yandex Cloud (для Search API), если переходим на продакшен-движок; (2) Core API endpoints для записи результатов.

---

## 8. Зависимости (pyproject.toml)

```toml
# Добавить в [project.dependencies]
"duckduckgo-search>=7.0",    # MVP: бесплатный веб-поиск, без API key

# Добавить в [project.optional-dependencies]
yandex = ["yandex-search-api>=0.2"]   # Production: Yandex Cloud Search API
```

---

## 9. Оценка стоимости

| Ресурс | MVP (DuckDuckGo) | Production (Yandex) |
|--------|-------------------|---------------------|
| Поисковые запросы | ~10 000 | ~10 000 |
| Стоимость поиска | $0 | ~$10–15 |
| HEAD-проверки (httpx) | ~20 000 | ~20 000 |
| DeepSeek (верификация) | ~$1–2 (опционально) | ~$1–2 |
| **Итого** | **~$0** | **~$12–17** |

Для сравнения: стоимость полного прохода Harvester по 5 000 org_website — $2.51 (Sprint 3.6 экстраполяция).

---

## 10. Риски и митигации

| Риск | Митигация |
|------|-----------|
| DuckDuckGo rate-limiting при массовом поиске | Задержка 2–3 сек между запросами; переход на Yandex API для >100 запросов |
| Поисковик находит не тот сайт (тёзки организаций) | Верификация: HEAD-проверка + быстрый crawl на совпадение названия/ИНН. Опционально: LLM-проверка через DeepSeek |
| ~~Yandex API требует юрлицо для Cloud-аккаунта~~ | ~~Снят: аккаунт Yandex Cloud с юрлицом уже есть~~ |
| Соцсети вместо сайта: VK/OK-группы содержат меньше структурированных данных | Для VK/OK расширить site_extractors (аналог SocinfoExtractor). Phase 2: VK API для стены группы |
| Core API endpoints для записи source ещё не реализованы | Mock mode в core_client; параллельно разработать endpoints в Laravel |

---

## 11. Связь с бэклогом Harvester v1

Этот план расширяет бэклог из `docs/Harvester_v1_Development_Plan.md` §11:

| Существующая задача | Как связано |
|--------------------|-------------|
| **H3** (Firecrawl fallback) ✅ | Firecrawl используется и для верификации найденных URL |
| **B5** (vk_group_url → vk_group_id) | Решается заодно: social_classifier извлекает ID |
| **B7** (GET organizers by source_id) | Расширяется: нужен PATCH source + POST source |
| **4.6** (Первый полный проход) | Зависит от обогащения: чем больше валидных URL, тем больше покрытие |

---

## 12. Будущее использование модуля `search/`

Веб-поиск — универсальный инструмент, применимый за пределами обогащения org_website:

1. **Phase 2 — обнаружение новых организаций:** поиск по запросам «КЦСОН {город}», «центр социального обслуживания {регион}» → match_or_create.
2. **Верификация данных:** проверка ИНН/ОГРН через поиск в ЕГРЮЛ; подтверждение адреса через 2GIS/Яндекс.Карты.
3. **Мониторинг изменений:** периодический поиск для обнаружения переезда сайта организации на новый домен.
4. **Source proposals (B8 из бэклога):** AI-агент предлагает новые источники на основе поиска.
5. **Enrichment из агрегаторов:** поиск организации на bus.gov.ru, ФПГ, Добро.рф.

---

## 13. Чек-лист перед стартом Sprint 5a

**Решения (подтверждены 2026-02-24):**

- [x] DuckDuckGo (MVP) → потом Yandex. Google fallback не нужен.
- [x] SQL-аудит: агент выполняет самостоятельно (через Core API или скрипт).
- [x] Core API: PATCH source / POST source реализовывать сразу.
- [x] Приоритет: сначала URL fix (категория A).
- [x] Ключ Yandex Cloud: после MVP. Аккаунт с юрлицом уже есть.
