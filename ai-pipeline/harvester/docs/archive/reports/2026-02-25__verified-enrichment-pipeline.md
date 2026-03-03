# Verified Enrichment Pipeline — Sprint 5.2

- **Дата:** 2026-02-25
- **Git commit:** 5110c01 (develop)
- **Область:** ai-pipeline/harvester/search/
- **Источник истины:** docs/2026-02-24__web-search-source-enrichment-plan.md

## Проблема

Sprint 5.1 реализовал поиск URL через Yandex Search API с 98% находимостью (168/171).
Однако ручная проверка показала **низкое качество** найденных URL:

| Проблема                    | Кол-во | % от 168 |
|-----------------------------|--------|----------|
| Агрегатор (checko, allpans) | 19     | 11%      |
| Чужая организация           | 49     | 29%      |
| Не главная страница         | 41     | 24%      |
| Ссылка Яндекс.Картинки     | 1      | 1%       |
| **Надёжные (root, score 100+)** | **58** | **35%** |

Вывод: поисковая выдача без верификации непригодна для автоматического обновления БД.

## Решение — 3-уровневый pipeline

### Уровень 1: Pre-filter (мгновенно, без сети)
**Файл:** `search/candidate_filter.py`

- Расширенный список агрегаторов (20+ доменов): checko, rusprofile, allpans, vsekcson, meddoclab, navigator.vnuki.fund и др.
- Фильтрация junk URL (Яндекс.Картинки, Google Search, Maps)
- Нормализация к корню домена: `soc13.ru/pi_purkaevo/news` → `soc13.ru/`
- Дедупликация по домену

### Уровень 2: Site Verifier (crawl + LLM, ~2K токенов)
**Файл:** `search/site_verifier.py`

- Краулит только **главную страницу** кандидата (Crawl4AI, одна страница)
- Верификационный промпт DeepSeek: «Это официальный сайт [название]?»
- Контекст сектора: соц. обслуживание, ПНИ, КЦСОН и т.п.
- Возвращает: `{is_official_site, is_main_page, org_name_found, confidence, reasoning}`
- Стоимость: **~2K токенов** вместо 30K полного pipeline ≈ **$0.0001/проверку**
- Early stop при confidence ≥ 0.8 на главной странице

### Уровень 3: Full Harvest (по запросу)
Подключается через `--harvest` flag:
- `MultiPageCrawler` → `OrganizationProcessor` → DaData → Core API
- Полная категоризация, извлечение контактов/мероприятий

### Social Media Fallback
Если сайт не найден:
1. Поиск VK-группы: `"[название] [город] вконтакте"`
2. Поиск OK-группы: `"[название] [город] одноклассники"`
3. Опционально: верификация соцсети через crawl + LLM

## Результаты тестов (5 URL)

| # | Организация | URL | Conf | Комментарий |
|---|---|---|---|---|
| 1 | ГАУСО ЧПНДИ | chita-pndi.zabguso.ru ✓ | 0.70 | По домену |
| 2 | ООО Республика | respublica.ru ✗ | 0.00 | Корректно отклонён — магазин |
| 3 | Хадабулакский ПНДИ | hadabulak-pndi.zabguso.ru ✓ | 0.70 | По домену |
| 4 | Томаровский ПНИ | tomarovinternat.ru ✓ | 0.90 | По названию |
| 5 | Кумертауский ПНИ | kumertaupni.bashkortostan.ru ✓ | 1.00 | Идеальное совпадение |

**Точность: 80% verified (4/5), 1 social-only (корректно)**

## CLI

```bash
# Без верификации (как раньше)
python -m scripts.enrich_sources --fix-urls -i data/audit_truncated_urls.json

# С верификацией (crawl + LLM)
python -m scripts.enrich_sources --fix-urls-verified -i data/audit_truncated_urls.json

# С верификацией + полный harvest
python -m scripts.enrich_sources --fix-urls-verified --harvest -i data/audit_truncated_urls.json

# Поиск для орг без источников + верификация
python -m scripts.enrich_sources --find-missing-verified -i data/audit_no_source.json
```

Параметры:
- `--verify-top N` — сколько кандидатов проверять (default: 3)
- `--harvest` — запустить полный pipeline на верифицированных URL
- `--offset N`, `--limit N` — для resume и батчевой обработки

## Стоимость

| Ресурс | На 1 орг | На 171 URL |
|--------|----------|------------|
| Yandex Search | 1-2 запроса | ~250 запросов |
| DeepSeek (verify) | ~2K токенов | ~340K токенов |
| DeepSeek (cost) | $0.0001 | ~$0.017 |
| Crawl4AI | 1-3 страницы | ~300 страниц |
| Время | ~20 сек | ~1 час |

## Новые файлы

```
search/
├── candidate_filter.py     # Level 1: pre-filter + URL normalization
├── site_verifier.py        # Level 2: crawl + LLM identity check
├── enrichment_pipeline.py  # Orchestrator: search → filter → verify → harvest
└── source_discoverer.py    # Updated: expanded aggregator list
scripts/
└── enrich_sources.py       # Updated: --fix-urls-verified, --find-missing-verified, --harvest
```

## Следующие шаги

1. Полный прогон 171 truncated URL с верификацией
2. Batch UPDATE в БД для верифицированных URL
3. Прогон ~2810 организаций без источников
4. Интеграция полного harvest (--harvest) для автоматической категоризации
