# Спецификация Dadata-клиента (Python, Harvester)

> **Модуль:** `ai-pipeline/harvester/enrichment/dadata_client.py`  
> **PHP-аналог:** `backend/app/Services/VenueAddressEnricher/VenueAddressEnricher.php`,  
> `backend/app/Services/Dadata/DadataClient.php`  
> **Дата:** 2026-02-24  
> **Источник истины по модели адресов:** `backend/docs/address_enrichment_via_dadata.md`

---

## 1. Назначение

Python-клиент для Dadata API, решающий две задачи:

1. **Геокодирование адресов** — по строке `address_raw` получить:
   - `fias_id` на уровне населённого пункта (для фильтра по городу в API)
   - `city_fias_id` (для фильтра `city_fias_id` в `GET /api/v1/organizations`)
   - `geo_lat`, `geo_lon` (координаты для фильтра по радиусу)
   - `region_iso`, `region_code`, `kladr_id`, `fias_level`

2. **Поиск организации по ИНН/ОГРН** (`find_party_by_id`) — дозаполнение названия, юрадреса, контактов.

---

## 2. API Dadata: два режима геокодирования

| Режим | Endpoint | Стоимость | Когда используется |
|-------|----------|-----------|-------------------|
| **suggest** (по умолчанию) | `suggestions.dadata.ru/suggestions/api/4_1/rs/suggest/address` | Бесплатно, 10K/день (растёт с подпиской) | Всегда, если есть `DADATA_API_KEY` |
| **clean** (opt-in) | `cleaner.dadata.ru/api/v1/clean/address` | Платно за каждый вызов | Только при `DADATA_USE_CLEAN=true` + `DADATA_SECRET_KEY`. Также как fallback если suggest вернул пустой ответ |

### Fallback-цепочка

```
suggest(address_raw)
  ├─ вернул данные → _map_data_to_result()
  └─ вернул null
       ├─ есть secret_key → clean(address_raw)
       │    ├─ вернул данные → _map_data_to_result()
       │    └─ вернул null → GeocodingResult(address_raw=..., всё остальное null)
       └─ нет secret_key → GeocodingResult(address_raw=..., всё остальное null)
```

### Env-переменные

```
DADATA_API_KEY=...        # обязательно для работы клиента
DADATA_SECRET_KEY=...     # нужен для clean API
DADATA_USE_CLEAN=false    # true = clean по умолчанию (вместо suggest)
```

При пустом `DADATA_API_KEY` клиент работает в passthrough-режиме: все вызовы возвращают `GeocodingResult(address_raw=...)` без обогащения. Пайплайн не ломается.

---

## 3. Маппинг ответа Dadata → GeocodingResult

### 3.1. fias_id: уровень населённого пункта, не дома

**Критически важно:** в venues.fias_id мы храним ФИАС-код **населённого пункта** (село, город, регион), а не дома или улицы. Это нужно для фильтра API `city_fias_id`, который ищет по `WHERE fias_id LIKE :city_fias_id%`.

Dadata в ответе возвращает несколько уровней fias_id:

| Поле Dadata | Уровень | Пример |
|-------------|---------|--------|
| `settlement_fias_id` | населённый пункт (посёлок, село, деревня) | `fbaca6ad-5c19-4702-a015-d1488f2ce143` |
| `city_fias_id` | город | `023484a5-f98d-4849-82e1-b7e0444b54ef` |
| `region_fias_id` | регион (область, край, республика) | `ed36085a-b2f5-454f-b9a9-1c9a678ee618` |

**Логика выбора** (`_pick_settlement_or_city_fias_id`):

```
fias_id = settlement_fias_id   # приоритет 1: самый точный НП
        ?? city_fias_id         # приоритет 2: город
        ?? region_fias_id       # приоритет 3: регион (если город не определён)
```

**PHP-аналог:** `VenueAddressEnricher::pickSettlementOrCityFiasId()`

### 3.2. fias_level

Определяется по тому, какой уровень fias_id мы сохранили:

| Условие | fias_level | Значение |
|---------|------------|----------|
| Есть `settlement_fias_id` | `"6"` | населённый пункт |
| Есть `city_fias_id` (нет settlement) | `"4"` | город |
| Есть `region_fias_id` (нет city и settlement) | `"1"` | регион |

**PHP-аналог:** `VenueAddressEnricher::pickFiasLevelForStoredId()`

### 3.3. city_fias_id: для фильтра API «по городу»

`city_fias_id` — отдельное поле в venues, используемое для фильтра `GET /api/v1/organizations?city_fias_id=...`. Может отличаться от `fias_id` (например, fias_id = посёлок, city_fias_id = вышестоящий город).

**Базовое значение:** из поля `data["city_fias_id"]` ответа Dadata.

**Fallback-логика** (если `city_fias_id` пустой):

| Условие | city_fias_id = | Причина |
|---------|----------------|---------|
| Федеральный город (RU-MOW, RU-SPE, RU-SEV) и fias_level=1 | `fias_id` | Москва/СПб/Севастополь — регион и город совпадают |
| Населённый пункт (fias_level=6) без города | `fias_id` | Позволяет фильтровать по НП когда города нет |
| Регион (fias_level=1), не федеральный город | `fias_id` | Позволяет фильтровать по региону когда города нет |

**PHP-аналоги:** `VenueAddressEnricher::pickCityFiasId()`, `mapDataToResult()` (строки 118-132)

**Известное ограничение:** PHP-реализация дополнительно делает вторичный suggest-запрос по названию города, извлечённому из адреса regex'ом (например, «г. Вологда, ул. Козлёнская» → suggest("Вологда") → city_fias_id). В Python-клиенте этот secondary lookup пока не реализован. На практике `city_fias_id` обычно приходит из первого suggest'а. Если при реальном тестировании окажется, что city_fias_id часто пустой — нужно будет добавить.

### 3.4. region_iso и region_code

| Поле | Откуда | Пример |
|------|--------|--------|
| `region_iso` | `data["region_iso_code"]` | `RU-VLG`, `RU-MOW` |
| `region_code` | `data["region_fias_id"]` **только когда region_iso_code = null** | UUID региона |

`region_code` нужен для **новых регионов** (ЛНР, ДНР, Херсон, Запорожье), у которых Dadata не возвращает ISO-код. Фильтрация в API: `GET /api/v1/organizations?region_code=...`.

**PHP-аналог:** `VenueAddressEnricher::pickRegionCode()`

### 3.5. kladr_id

Берётся наиболее специфичный из доступных:

```
house_kladr_id → street_kladr_id → settlement_kladr_id → city_kladr_id → region_kladr_id → kladr_id
```

**PHP-аналог:** `VenueAddressEnricher::pickKladrId()`

### 3.6. Координаты

`geo_lat` и `geo_lon` берутся из одноимённых полей ответа Dadata. Могут приходить как строки — конвертируются через `_safe_float()`.

---

## 4. Поиск организации (findPartyById)

| Параметр | Значение |
|----------|----------|
| Endpoint | `suggestions.dadata.ru/suggestions/api/4_1/rs/findById/party` |
| Вход | ИНН (10/12 цифр) или ОГРН (13/15 цифр) |
| Стоимость | Бесплатно (входит в suggest tier) |
| Ответ | `PartyResult(inn, ogrn, name_full, name_short, address, phones, emails, status)` |

Используется для:
- Верификации ИНН/ОГРН, извлечённых LLM
- Дозаполнения юридического названия и адреса
- Получения контактных данных из ЕГРЮЛ

**PHP-аналог:** `DadataClient::findPartyById()`, используется в `artisan organizations:enrich-from-dadata`

---

## 5. Обработка ошибок и retry

| Ситуация | Поведение |
|----------|-----------|
| Нет `DADATA_API_KEY` | Passthrough — возвращается `GeocodingResult(address_raw=...)` без обогащения |
| Сетевая ошибка (ConnectError, Timeout) | 3 попытки с exponential backoff (1→2→4→10 сек) |
| Dadata вернул пустой ответ | Без retry, возвращается passthrough |
| Любое другое исключение | Логируется warning, возвращается passthrough |

Пайплайн **никогда не падает** из-за Dadata — все ошибки деградируют до passthrough.

---

## 6. Связь с ImportController и venues

### Что Harvester отправляет в Core API

```json
{
  "venues": [{
    "address_raw": "г. Вологда, ул. Козлёнская, д. 35",
    "address_comment": "3 этаж",
    "fias_id": "023484a5-...",        // из GeocodingResult.fias_id
    "geo_lat": 59.2239,               // из GeocodingResult.geo_lat
    "geo_lon": 39.8842                // из GeocodingResult.geo_lon
  }]
}
```

### Что ImportController делает с этим

1. `Venue::firstOrCreate` с ключом `fias_id` (если есть) или `address_raw` (fallback)
2. Сохраняет `address_raw`, `fias_id`
3. Устанавливает координаты через PostGIS (`ST_MakePoint`)
4. **НЕ сохраняет** `fias_level`, `city_fias_id`, `region_iso`, `region_code`

### Что дополняет artisan-команда

После импорта администратор запускает:

```bash
php artisan venues:enrich-addresses --limit=500
```

Команда дополняет: `fias_level`, `city_fias_id`, `kladr_id`, `region_iso`, `region_code`, координаты. Использует ту же логику (VenueAddressEnricher), которую мы воспроизводим в Python.

### TODO: расширить ImportController

Чтобы не требовать повторный вызов Dadata из artisan, ImportController нужно расширить для приёма и сохранения `fias_level`, `city_fias_id`, `region_iso`, `region_code`. Тогда Python-клиент будет передавать все поля, и обогащение через artisan не потребуется.

---

## 7. Диаграмма потока данных

```
address_raw (из LLM / OrganizationOutput)
    │
    ▼
DadataClient.geocode(address_raw)
    │
    ├── suggest API (бесплатно, 10K/день)
    │     └── fallback → clean API (если suggest пуст и есть secret_key)
    │
    ▼
Raw Dadata response (JSON dict)
    │
    ▼
_map_data_to_result()
    ├── _pick_settlement_or_city_fias_id()   → fias_id (НП/город/регион)
    ├── _pick_fias_level()                    → "6" / "4" / "1"
    ├── _pick_city_fias_id()                  → city_fias_id + fallback'и
    │     ├── Федеральные города: city = fias_id
    │     ├── Сёла без города: city = fias_id
    │     └── Регионы без города: city = fias_id
    ├── _pick_region_code()                   → region_code (для новых регионов без ISO)
    ├── _pick_kladr_id()                      → наиболее специфичный КЛАДР
    └── geo_lat, geo_lon                      → координаты
    │
    ▼
GeocodingResult
    │
    ▼
to_core_import_payload(org, geo_results=[...])
    │
    ▼
POST /api/internal/import/organizer
    venues: [{ address_raw, fias_id, geo_lat, geo_lon }]
```

---

## 8. Тесты

**Файл:** `tests/test_dadata_client.py` (47 тестов)

| Группа | Что проверяет |
|--------|---------------|
| `TestDadataClientDisabled` | Passthrough без ключей |
| `TestDadataClientEnabled` | Режимы suggest/clean, opt-in |
| `TestFindPartyDisabled` | findPartyById без ключей |
| `TestPickSettlementOrCityFiasId` | Приоритет settlement → city → region |
| `TestPickFiasLevel` | Уровни 6/4/1 |
| `TestPickCityFiasId` | Прямое извлечение |
| `TestPickRegionCode` | Новые регионы без ISO |
| `TestPickKladrId` | Цепочка приоритетов КЛАДР |
| `TestMapDataToResult` | Полный маппинг: город, село, федеральный город, новый регион, регион без города |
| `TestSafeFloat`, `TestStrOrNone` | Утилиты |
| `TestBatchGeocoding` | Пакетная обработка |
