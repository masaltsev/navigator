# Фильтрация Venues: Обзор логики

## Структура данных в таблице `venues`

### Основные поля для фильтрации:

| Поле | Тип | Описание | Источник |
|------|-----|----------|----------|
| `address_raw` | string | Исходный адрес (текст) | Импорт из WP |
| `fias_id` | UUID (nullable, indexed) | FIAS ID населённого пункта/города/региона | DaData API |
| `fias_level` | string (nullable) | Уровень FIAS: `'6'` (населённый пункт), `'4'` (город), `'1'` (регион) | Вычисляется из DaData |
| `city_fias_id` | UUID (nullable, indexed) | **FIAS ID города** для фильтрации по городу в API | DaData или `fias_id` (если level 4/6) |
| `region_iso` | string (nullable, indexed) | Код региона (ISO, например `RU-VLG`, `RU-MOW`) | DaData API |
| `coordinates` | geometry(Point, 4326) | Геокоординаты (PostGIS) | DaData API или WP lat/lng |
| `kladr_id` | string (nullable, indexed) | KLADR ID | DaData API |

### Логика заполнения полей:

1. **`fias_id`** — хранит FIAS ID **населённого пункта** (приоритет: settlement → city → region)
   - Уровень 6: населённый пункт (микрорайон, посёлок)
   - Уровень 4: город
   - Уровень 1: регион (для Москвы, СПб, Севастополя)

2. **`fias_level`** — уровень объекта, сохранённого в `fias_id` (6/4/1)

3. **`city_fias_id`** — **всегда FIAS ID города** для фильтрации:
   - Если DaData вернул `city_fias_id` → используем его
   - Если `fias_level = 4 или 6` → `city_fias_id = fias_id`
   - Если `fias_level = 1` (города-субъекты: Москва, СПб, Севастополь) → `city_fias_id = fias_id`
   - Если `city_fias_id` отсутствует → пытаемся извлечь название города из адреса и сделать suggest

4. **`coordinates`** — PostGIS Point (lat/lng) для геопоиска

---

## Фильтрация в API (`OrganizationController`)

### 1. Фильтр по городу: `city_fias_id` или `city_fias_id[]`

**Параметры запроса:**
```
GET /api/v1/organizations?city_fias_id=023484a5-f98d-4849-82e1-b7e0444b54ef
GET /api/v1/organizations?city_fias_id[]=id1&city_fias_id[]=id2
```

**Логика фильтрации:**
```php
// 1. Приоритет: venue.city_fias_id (если заполнен)
whereIn('city_fias_id', $cityFiasIds)

// 2. Fallback для legacy данных: venue.fias_id (если city_fias_id пустой)
orWhere(function ($q) {
    $q->whereNull('city_fias_id')
      ->where('fias_id', 'LIKE', $cityFiasId . '%');
})
```

**Пример:** Клиент стандартизирует "Вологда" → получает один FIAS ID → передаёт в API → получает все организации в Вологде.

---

### 2. Геопоиск по радиусу: `lat`, `lng`, `radius_km`

**Параметры запроса:**
```
GET /api/v1/organizations?lat=59.2181&lng=39.8887&radius_km=5
```

**Логика фильтрации:**
```php
// PostGIS: ST_DWithin для поиска в радиусе
whereHas('venues', function ($q) use ($lat, $lng, $radiusMeters) {
    $q->whereRaw(
        'ST_DWithin(coordinates, ST_MakePoint(?, ?)::geography, ?)',
        [$lng, $lat, $radiusMeters]
    );
});
```

**Особенности:**
- Использует PostGIS функцию `ST_DWithin` с типом `geography` (расстояние в метрах)
- Радиус в км конвертируется в метры: `radius_km * 1000`
- Требует заполненное поле `coordinates` (PostGIS Point)

---

### 3. Другие фильтры (не связанные с venues)

- `thematic_category_id[]` — фильтр по тематическим категориям
- `organization_type_id[]` — фильтр по типам организаций
- `service_id[]` — фильтр по услугам
- `works_with_elderly` — фильтр по работе с пожилыми (по умолчанию `true`)

---

## Обогащение данных через DaData

### Команда: `php artisan venues:enrich-addresses`

**Режимы работы:**

1. **По адресу** (по умолчанию):
   - Использует `address_raw`
   - Сначала пытается `suggestAddress()` (Suggest API)
   - При ошибке/пустом ответе → fallback на `cleanAddress()` (Clean API)

2. **Только Clean API** (`--use-clean-only`):
   - Используется когда квота Suggest API исчерпана
   - Требует `DADATA_SECRET_KEY`

3. **По координатам** (`--by-geo`):
   - Для площадок без `address_raw`, но с `coordinates`
   - Использует `reverseGeocode()`

**Что заполняется:**
- `fias_id` (settlement/city/region)
- `fias_level` (6/4/1)
- `city_fias_id` (для фильтрации по городу)
- `region_iso` (код региона)
- `kladr_id`
- `coordinates` (если отсутствуют)

**Выборка для обработки** (без `--force`):
- Только "неполные" площадки: отсутствует хотя бы одно из полей (`fias_id`, `fias_level`, `city_fias_id`, `region_iso`, `coordinates`)

---

## Особые случаи

### Города-субъекты федерации (Москва, СПб, Севастополь)

- DaData возвращает `region_fias_id` (уровень 1) вместо `city_fias_id`
- **Решение:** При `fias_level = '1'` и `region_iso IN ('RU-MOW', 'RU-SPE', 'RU-SEV')` → `city_fias_id = fias_id`
- Это позволяет корректно фильтровать по городу в API

### Микрорайоны и населённые пункты

- Если площадка находится в микрорайоне (уровень 6), `fias_id` хранит FIAS микрорайона
- Но `city_fias_id` должен хранить FIAS города для фильтрации
- Пример: Вологодский микрорайон "Тепличный" → `fias_id` = микрорайон, `city_fias_id` = Вологда

---

## Индексы для производительности

- `venues.fias_id` — индекс для fallback фильтрации
- `venues.city_fias_id` — индекс для основной фильтрации по городу
- `venues.region_iso` — индекс для потенциальной фильтрации по региону
- `venues.coordinates` — GiST индекс для геопоиска (PostGIS)

---

## Примеры использования

### Фильтр по городу Вологде:
```http
GET /api/v1/organizations?city_fias_id=023484a5-f98d-4849-82e1-b7e0444b54ef
```

### Геопоиск в радиусе 5 км от центра Вологды:
```http
GET /api/v1/organizations?lat=59.2181&lng=39.8887&radius_km=5
```

### Комбинация фильтров:
```http
GET /api/v1/organizations?city_fias_id=023484a5-f98d-4849-82e1-b7e0444b54ef&thematic_category_id[]=1&works_with_elderly=true
```
