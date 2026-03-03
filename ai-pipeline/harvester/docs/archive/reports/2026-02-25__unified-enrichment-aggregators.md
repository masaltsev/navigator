# Отчёт: унификация потока обогащения агрегаторов

**Дата:** 2026-02-25  
**Git commit:** 5110c01  
**Область:** Harvester, агрегаторы (ФПГ, СО НКО, Silver Age), EnrichmentPipeline  
**Источник истины:** `docs/Navigator_Core_Model_and_API.md`, `docs/AI_Pipeline_Navigator_Plan.md`, `ai-pipeline/harvester/docs/aggregators_guide.md`

---

## Резюме

Проведена унификация потока поиска сайтов и обогащения организаций для всех трёх агрегаторов (ФПГ, СО НКО, Silver Age). Вместо дублирования логики в каждом пайплайне теперь используется общий **EnrichmentPipeline** (поиск → верификация → полный harvest с учётом контекста агрегатора). Добавлены **контекстные блоки** (практики ФПГ/СОНКО/Silver Age), которые передаются в LLM при классификации и сохраняются при обновлении уже найденных организаций.

---

## 1. Цели изменений

1. **Единый поток discovery** — все агрегаторы используют один и тот же конвейер: поиск сайта (DuckDuckGo / Yandex v2) → предфильтр → верификация → полный harvest с SiteExtractorRegistry и социальным fallback.
2. **Сохранение контекста агрегатора** — описание практик (Silver Age), проектов (ФПГ) и реестровых данных (СОНКО) передаётся в LLM как `additional_context` и используется при классификации и формировании описания организации.
3. **Обогащение уже найденных организаций** — при совпадении организации в Core (match по ИНН / `source_reference`) выполняется обновление записи: дополнение описания и `ai_source_trace` контекстом из агрегатора.
4. **Устранение дублирования** — удалены локальные реализации `_discover_website`, `_harvest_from_website`, `_prepare_harvest_text` из пайплайнов; общая логика сосредоточена в `search/enrichment_pipeline.py`.

---

## 2. Изменения по компонентам

### 2.1 EnrichmentPipeline (`search/enrichment_pipeline.py`)

| Изменение | Описание |
|-----------|----------|
| **Параметры `enrich_missing_source()`** | Добавлены опциональные `additional_context: str = ""` и `source_kind: str = "org_website"`. Контекст передаётся в `_run_full_harvest()`. |
| **Параметры `enrich_broken_url()`** | Те же `additional_context` и `source_kind` для симметрии с основным сценарием. |
| **`_run_full_harvest()`** | Принимает `additional_context` и `source_kind`. Если контекст задан, он препендится к `raw_text` через разделитель `---` перед вызовом `OrganizationProcessor.process()`. В `HarvestInput` передаётся переданный `source_kind` вместо хардкода `"org_website"`. |
| **EnrichmentResult** | В dataclass добавлено поле `additional_context: str = ""` для прозрачности (опционально используется при сериализации). |

Итог: один и тот же пайплайн используется и для «организаций без источников» (`auto_enrich`), и для агрегаторов; агрегаторы передают свой контекст и тег источника.

### 2.2 Контекстные билдеры (Phase 2)

В каждом агрегаторе добавлен статический метод, формирующий текстовый блок для LLM:

| Агрегатор | Метод | Содержимое |
|-----------|--------|------------|
| **Silver Age** | `_build_practice_context(org)` | Заголовок «Контекст из агрегатора silveragemap.ru», название и регион организации, категории практик, до 5 практик с названием и описанием (до 500 символов), напоминание о фокусе на старшем возрасте. |
| **ФПГ** | `_build_project_context(org)` | Заголовок «Контекст из каталога Фонда президентских грантов», ИНН/ОГРН, регион, грантовые направления, до 5 проектов с названием, направлением, статусом и суммой гранта, напоминание о ключевых словах про пожилых. |
| **СОНКО** | `_build_sonko_context(org)` | Заголовок «Контекст из реестра СО НКО», полное/сокращённое название, ИНН/ОГРН, адрес, ОКВЭД, ОПФ, статусы СОНКО и критерии включения, напоминание о фильтрации по ОКВЭД/ключевым словам. |

Формат вывода — многострочный текст с явными метками полей. Он подставляется **перед** контентом сайта в одном запросе к LLM, чтобы модель учитывала и реестровые данные, и содержимое страницы.

### 2.3 Silver Age Pipeline (`aggregators/silverage/silverage_pipeline.py`)

- **Lookup:** перед поиском сайта выполняется попытка получить ИНН через `DadataClient.suggest_party(org.name, region=org.region)`. При наличии ИНН — `lookup_organization(inn=..., source_reference=...)`, иначе только по `source_reference`.
- **Совпадение в Core:** при найденной организации вызывается `_update_matched_org(existing, org, context)` — дополнение описания и `ai_source_trace` данными из Silver Age (описание практик, список практик).
- **Новая организация:** используется `EnrichmentPipeline.enrich_missing_source(org_title=..., city=..., inn=..., source_id=..., additional_context=context, source_kind="platform_silverage")`. При успехе и наличии `harvest_output` payload дообогащается `source_reference` и при необходимости `inn`, затем `import_organizer` и создание source через `_create_source_record`.
- **Fallback:** при отсутствии или неуспехе EnrichmentPipeline вызывается `_create_minimal_org(org, inn=inn)`. В минимальную запись при известном ИНН подставляются данные из `find_party_by_id` (в т.ч. гео через `to_geocoding_result()`).
- **Удалено:** `_discover_website`, `_harvest_from_website`, `_prepare_harvest_text`; добавлен ленивый `_get_enrichment_pipeline()`.

### 2.4 FPG Pipeline (`aggregators/fpg/fpg_pipeline.py`)

- **Lookup:** без изменений — по ИНН и `source_reference`.
- **Совпадение в Core:** добавлен вызов `_update_matched_org(existing, org, context)` — в описание и trace дописываются проекты ФПГ и направление гранта.
- **Новая организация:** вызов `EnrichmentPipeline.enrich_missing_source(..., additional_context=context, source_kind="registry_fpg")`. При успехе — сборка payload из `harvest_output` с подстановкой `source_reference`, `inn`, `ogrn` и `import_organizer` + `_create_source_record`.
- **Fallback:** при отсутствии pipeline или неуспехе enrichment — по-прежнему `_create_minimal_org(org)` с Dadata и гео из `party.to_geocoding_result()`.
- **Удалено:** `_discover_website`, `_harvest_from_website`, `_prepare_harvest_text`, `_build_payload`; добавлен `_get_enrichment_pipeline()`.

### 2.5 SONKO Pipeline (`aggregators/sonko/sonko_pipeline.py`)

- Аналогично ФПГ: при совпадении — `_update_matched_org` с контекстом СОНКО (статусы, ОКВЭД); при новой организации — `enrich_missing_source(..., additional_context=context, source_kind="registry_sonko")`.
- **Удалено:** `_discover_website`, `_harvest_from_website`, `_prepare_harvest_text`, `_build_payload`; добавлен `_get_enrichment_pipeline()`.

### 2.6 Обновление совпавших организаций (`_update_matched_org`)

Во всех трёх пайплайнах реализован метод с одной и той же идеей:

1. Взять текущие `title`, `description`, `ai_metadata` из ответа Core (existing).
2. Сформировать payload с `source_reference` агрегатора, обновлённым `description` (старое описание + блок «Дополнительно из …» с контекстом агрегатора) и расширенным `ai_source_trace` (добавление записи с `source_kind` агрегатора и перечнем полей).
3. Вызвать `import_organizer(payload)` — Core выполняет update по `source_reference`/ИНН, описание и trace обогащаются без создания дубликата.

Таким образом, повторный прогон агрегатора не только находит уже существующие организации, но и дополняет их реестровым/практическим контекстом.

---

## 3. Схема потока (после изменений)

```
Агрегатор (ФПГ / СОНКО / Silver Age)
  │
  ├─ Parse/Scrape → Filter → Group by org
  │
  ▼
  Для каждой организации:
  │
  ├─ [Silver Age only] suggest_party(name, region) → inn (опционально)
  ├─ lookup_organization(inn?, source_reference) → existing?
  │
  ├─ context = _build_*_context(org)   # practice / project / sonko
  │
  ├─ if existing:
  │     _update_matched_org(existing, org, context)  → return
  │
  ├─ pipeline = _get_enrichment_pipeline()  # EnrichmentPipeline(provider, llm)
  ├─ enrichment = pipeline.enrich_missing_source(
  │       org_title, city, inn?, source_id=source_reference,
  │       additional_context=context, source_kind=...)
  │
  ├─ if enrichment.success and enrichment.harvest_output:
  │     payload = harvest_output + source_reference + inn/ogrn
  │     import_organizer(payload)
  │     _create_source_record(organizer_id, verified_url)
  │     return
  │
  └─ _create_minimal_org(org)  # или _create_minimal_org(org, inn) для Silver Age
```

EnrichmentPipeline внутри выполняет: `discover_sources` → фильтр и дедуп кандидатов → `SiteVerifier.verify_batch` → выбор лучшего кандидата → при tier AUTO — `_run_full_harvest` с препендом `additional_context` к `raw_text` и переданным `source_kind`.

---

## 4. Тестирование

- **Общие тесты:** 399 тестов (в т.ч. с игнором test_harvest_api, test_integration_deepseek, test_yandex_xml_provider) проходят.
- **Агрегаторы:**  
  - `test_silverage_pipeline.py` — группировка, отчёт, `_build_practice_context` (содержимое, лимит 5 практик, упоминание старшего возраста), dry-run, создание минимальной организации при отсутствии enrichment, обработка ошибок, обновление совпавшей организации.  
  - `test_fpg_pipeline.py` — `_build_project_context`, analyze, dry-run, mock mode, обновление совпавшей организации.  
  - `test_sonko_pipeline.py` — `_build_sonko_context`, analyze, dry-run, mock mode, обновление совпавшей организации.

Все 41 тест по трём пайплайнам проходят.

---

## 5. Обратная совместимость

- CLI и Celery-задачи агрегаторов не менялись; аргументы и контракты прежние.
- Формат отчётов (PipelineReport, to_dict) сохранён.
- Core API вызывается в том же виде (`import_organizer`, `create_source`, `lookup_organization`); расширены только передаваемые payload (description, ai_source_trace при update).

---

## 6. Связанные документы

- **Руководство по агрегаторам:** `ai-pipeline/harvester/docs/aggregators_guide.md` — дополнен разделом про унифицированный поток и контекст (см. обновление ниже).
- **Отчёт по Verified Enrichment Pipeline:** `ai-pipeline/harvester/docs/reports/2026-02-25__verified-enrichment-pipeline.md`.
- **Source CRUD и auto-enrich:** `ai-pipeline/harvester/docs/reports/2026-02-25__source-crud-api-auto-enrich.md`.

---

## 7. Итог

Поток обогащения для агрегаторов унифицирован: один EnrichmentPipeline, общие контекстные билдеры и единообразное обновление совпавших организаций. Контекст агрегатора (практики, проекты, реестр) используется при классификации и сохраняется в описании и ai_source_trace, что улучшает качество данных и прослеживаемость источников.
