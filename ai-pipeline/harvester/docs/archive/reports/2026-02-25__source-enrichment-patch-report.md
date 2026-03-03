# Отчёт: обогащение и патч источников (org_website) — Sprint 5

- **Дата:** 2026-02-25
- **Commit:** 5110c01
- **Область:** AI Pipeline / Harvester — поиск и верификация сломанных URL источников
- **Источник истины:** `docs/Navigator_Core_Model_and_API.md`, `docs/2026-02-24__web-search-source-enrichment-plan.md`

---

## 1. Цель

Восстановить рабочие URL для 171 источника (`sources.kind = 'org_website'`), у которых `base_url` был обрезан (truncated) и не вёл на реальный сайт.

## 2. Пайплайн

Трёхуровневый верифицированный пайплайн:

1. **Поиск** — Yandex Cloud Search API v2 по доменному фрагменту + названию организации
2. **Pre-filter** — отсев агрегаторов, нормализация URL, дедупликация
3. **Верификация** — crawl страницы + LLM-проверка (DeepSeek, ~2K токенов): совпадение названия, домена, ИНН
4. **Harvest** (для AUTO) — полный обход сайта, категоризация, извлечение данных организации
5. **Social fallback** — поиск VK/OK/Telegram, если сайт не найден

### Confidence tiers

| Tier | Критерий | Действие |
|------|----------|----------|
| **AUTO** | confidence >= 0.8 | Автоматический патч БД + harvest |
| **REVIEW** | 0.5 <= confidence < 0.8 | Ручная проверка перед патчем |
| **REJECT** | confidence < 0.5 или не найдено | Отклонено / только соцсети |

## 3. Результаты

### 3.1 Общая статистика

| Tier | Кол-во | % от 171 |
|------|--------|----------|
| **AUTO** | 110 | 64% |
| **REVIEW** | 21 | 12% |
| **REJECT** | 40 | 23% |

### 3.2 AUTO — патч применён

- **103 источника обновлены** (`sources.base_url` + `organizations.site_urls`)
- **7 дубликатов soft-deleted** (EISDU — один organizer, несколько источников → один обновлён, остальные удалены)
- Средний confidence: **0.93**
- Harvest decisions: 104 accepted, 2 rejected, 4 n/a

### 3.3 REVIEW — ожидает ручной проверки

21 элемент, средний confidence: **0.69**. Основные паттерны:

- Рязанская область (10+ организаций) — сайты на `ryazanszn.ru` с confidence ~0.7
- Переезды сайтов (ЧПНДИ → новый socinfo.ru домен)
- Неточное совпадение названий

### 3.4 REJECT — отклонены

| Причина | Кол-во |
|---------|--------|
| Только соцсети (VK/OK найдены, сайт — нет) | 31 |
| Полное отсутствие совпадений | 9 |

## 4. Стоимость

| Метрика | Значение |
|---------|----------|
| Yandex Search queries | ~500 |
| DeepSeek API calls | ~600 |
| DeepSeek cache hit rate (verify) | 75-100% |
| DeepSeek cache hit rate (harvest) | 85-100% |
| Ориентировочная стоимость DeepSeek | ~$0.50 |
| Yandex Search (480 руб/1000 запросов) | ~240 руб |
| Время выполнения | ~2 часа |

## 5. Бэкап и откат

```bash
# Бэкап создан перед патчем
ls data/backups/navigator_core_pre_enrichment_20260225_143446.dump

# Откат (если нужно)
pg_restore -h 127.0.0.1 -U navigator_core_user -d navigator_core --clean \
  data/backups/navigator_core_pre_enrichment_20260225_143446.dump
```

## 6. Файлы результатов

| Файл | Содержание |
|------|-----------|
| `data/results_171_merged_auto.json` | 110 AUTO-записей (применены) |
| `data/results_171_merged_review.json` | 21 REVIEW-запись |
| `data/results_171_merged_reject.json` | 40 REJECT-записей |
| `data/results_171_patch_audit.json` | Аудит-лог патча (old_url → new_url для каждой записи) |
| `data/results_171_merged_review_review_ready.json` | Шаблон для ручной проверки (с полями `approved`, `edited_url`, `notes`) |

## 7. Workflow ручной проверки (REVIEW)

### Вариант A: редактирование JSON

1. Открыть `data/results_171_merged_review_review_ready.json`
2. Для каждого элемента:
   - Проверить `verified_url` — корректный ли сайт
   - Проверить `reasoning` — аргументация LLM
   - Проверить `org_name_found` — совпадает ли с `org_title`
3. Установить:
   - `"approved": true` — для импорта
   - `"edited_url": "https://correct-url.ru/"` — если нужно заменить URL
   - `"notes": "комментарий"` — опционально
4. Запустить патч:

```bash
cd ai-pipeline/harvester
python -m scripts.patch_sources \
  --input data/results_171_merged_review_review_ready.json \
  --only-approved
```

### Вариант B: интерактивная CLI-проверка

```bash
cd ai-pipeline/harvester
python -m scripts.patch_sources \
  --input data/results_171_merged_review.json \
  --interactive
```

Для каждого элемента показывается карточка с данными, доступные действия:
- `a` — approve (принять)
- `r` — reject (отклонить)
- `e` — edit URL (ввести правильный URL вручную и принять)
- `s` — skip (пропустить, решить позже)
- `q` — quit (выйти, сохранить промежуточный результат)

Результат сохраняется в `*_reviewed.json`. Затем применить:

```bash
python -m scripts.patch_sources \
  --input data/results_171_merged_review_reviewed.json \
  --only-approved
```

### Dry-run

Для предварительного просмотра изменений без записи в БД:

```bash
python -m scripts.patch_sources \
  --input data/results_171_merged_review_review_ready.json \
  --only-approved --dry-run
```

## 8. Что обновляется при патче

Для каждого approved элемента:

1. **`sources.base_url`** — заменяется на verified URL
2. **`sources.name`** — обновляется на доменное имя нового URL
3. **`sources.last_status`** — сбрасывается на `'pending'` (готов к промышленному обходу)
4. **`organizations.site_urls`** — JSONB массив: старый URL удаляется, новый добавляется
5. При конфликте уникальности `(organizer_id, base_url)` — дубликат soft-deleted

## 9. Социальные сети из REJECT-записей

Из 31 организации с найденными соцсетями (но без сайта):

1. **Отсеяны**: 10 EISDU (VK платформы, не организации), 12 личных страниц/постов
2. **Верифицированы LLM**: 20 кандидатов (26 страниц) → crawl + LLM-проверка
3. **Результат**: **12 организаций, 15 страниц** подтверждены и **созданы как источники** в БД

| Платформа | Создано |
|-----------|---------|
| `vk_group` | 8 |
| `ok_group` | 7 |

Отклонены 8 орг. (VK-страницы без контента или с несовпадающими названиями).

Файлы:
- `data/social_verified.json` — результаты верификации соцсетей
- `data/social_verify_candidates.json` — входные кандидаты (после фильтрации)

## 10. Известные edge cases

1. **Новосибирск** — 5 районных КЦСОН → один портал `social.novo-sibirsk.ru`. Все обновлены на одинаковый URL (разные organizer_id, constraint не нарушен).
2. **EISDU** — 8 источников одного organizer → 1 обновлён на `eisdu.ru`, 7 soft-deleted.
3. **URLs с `/about`** — некоторые verified_url ведут не на корень (`/about`). При промышленном обходе `multi_page` стратегия начнёт с этой страницы и найдёт остальные.
4. **13 "сирот"** — источники без `organizer_id`. Обновлён только `sources.base_url`, `organizations.site_urls` не затронут (нет связи).
