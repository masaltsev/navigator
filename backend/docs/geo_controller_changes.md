
## 1. Общие принципы

1. **Структуру БД не трогаем.**
Поля `fias_id`, `city_fias_id`, `regioniso`, `coordinates` остаются как есть.

2. **API‑фильтры, которые нужно поддерживать:**
    - `city_fias_id` (строка или массив) — «город/населённый пункт»;
    - `regioniso` — регион по ISO‑коду, если есть;
    - `region_code` — новый параметр для регионов без ISO (ДНР/ЛНР/Херсон/Запорожье), будет храниться в venues как отдельное поле или в JSON (см. ниже);
    - `lat`, `lng`, `radius_km` — радиус на карте.
3. **Поведение для новых регионов (regioniso = null):**
    - При enrichment сохраняем помимо `regioniso` ещё и «сырой» код региона из Дадаты (`region_kladr_id` или `region_fias_id`) в новое поле `region_code` (string) в таблице `venues` — это отдельная миграция (можно сделать позже, но в инструкцию сразу закладываем).
    - В фильтре по региону:
        - если пришёл `regioniso` — фильтруем по `venues.regioniso`;
        - если пришёл `region_code` — фильтруем по `venues.region_code`;
        - для переходного периода допустим вариант, когда UI для новых регионов сразу шлёт `region_code`, не используя ISO.

***

## 2. OrganizationController: инструкция по изменениям

Ориентируемся на ваш текущий `index()`.

### 2.1. Расширить выборку venues

Сейчас в `with(['venues' => function ($q) { ... }])` выбирается:

```php
$q->select('venues.id', 'venues.address_raw', 'venues.coordinates', 'venues.fias_id')
```

**Задача для Cursor:** добавить сюда поля, которые нужны для GAR‑фильтрации на фронте:

- `venues.city_fias_id`
- `venues.regioniso`
- `venues.region_code` (после миграции)

```php
$q->select(
    'venues.id',
    'venues.address_raw',
    'venues.coordinates',
    'venues.fias_id',
    'venues.city_fias_id',
    'venues.regioniso',
    'venues.region_code'
)
->orderBy('organization_venues.is_headquarters', 'desc')
->limit(1);
```


### 2.2. Фильтр по works_with_elderly — оставить как есть

Этот блок корректный, изменений не требует.

### 2.3. Фильтр по city_fias_id — оставить, но чуть подчистить

Текущий код уже реализует нужный контракт: `city_fias_id` или массив, + fallback на `fias_id LIKE` для старых данных.

**Задача для Cursor:** только слегка отформатировать и обернуть в отдельный приватный метод для читаемости (по желанию), но по логике менять ничего не нужно:

```php
$cityFiasIds = $request->filled('city_fias_id')
    ? (array) $request->input('city_fias_id')
    : [];

if ($cityFiasIds !== []) {
    $cityFiasIds = array_filter(array_map('strval', $cityFiasIds));

    if ($cityFiasIds !== []) {
        $query->whereHas('venues', function ($q) use ($cityFiasIds) {
            $q->where(function ($q2) use ($cityFiasIds) {
                $q2->whereIn('city_fias_id', $cityFiasIds)
                   ->orWhere(function ($q3) use ($cityFiasIds) {
                       $q3->whereNull('city_fias_id')
                          ->where(function ($q4) use ($cityFiasIds) {
                              foreach ($cityFiasIds as $id) {
                                  $q4->orWhere('fias_id', 'LIKE', $id.'%');
                              }
                          });
                   });
            });
        });
    }
}
```


### 2.4. Новый фильтр по региону: regioniso + region_code

**Задача для Cursor:** сразу после блока `city_fias_id` добавить фильтрацию по региону.

Контракт:

- `GET /api/v1/organizations?regioniso=RU-MOW`
- `GET /api/v1/organizations?region_code=32` (пример для новых регионов, код условный)

Код:

```php
// Filter by region (ISO or raw region_code for new regions)
if ($request->filled('regioniso') || $request->filled('region_code')) {
    $regionIso = $request->input('regioniso');
    $regionCode = $request->input('region_code');

    $query->whereHas('venues', function ($q) use ($regionIso, $regionCode) {
        $q->where(function ($q2) use ($regionIso, $regionCode) {
            if ($regionIso !== null) {
                $q2->orWhere('regioniso', $regionIso);
            }

            if ($regionCode !== null) {
                $q2->orWhere('region_code', $regionCode);
            }
        });
    });
}
```

Логика обработки кейса «новые регионы»:

- для ДНР/ЛНР/Херсон/Запорожье Дадата сейчас отдаёт `region_iso_code = null`, но возвращает региональные идентификаторы (например, `kladr_id` / `fias_id`).
- вы храните их в `venues.region_code` (нужно будет доработать enrichment скрипт);
- фронт, если не видит `regioniso`, будет слать `region_code`, и фильтрация сработает.


### 2.5. Фильтры по тематике, типам, услугам — без изменений

Код по `thematic_category_id`, `organization_type_id`, `service_id` уже корректен.

### 2.6. Фильтр по радиусу — без логических изменений

Ваш текущий `ST_DWithin` уже соответствует схеме PostGIS:

```php
if ($request->filled(['lat', 'lng', 'radius_km'])) {
    $lat = $request->input('lat');
    $lng = $request->input('lng');
    $radiusKm = $request->input('radius_km');
    $radiusMeters = $radiusKm * 1000;

    $query->whereHas('venues', function ($q) use ($lat, $lng, $radiusMeters) {
        $q->whereRaw(
            'ST_DWithin(coordinates, ST_MakePoint(?, ?)::geography, ?)',
            [$lng, $lat, $radiusMeters]
        );
    });
}
```

**Задача для Cursor:** ничего не менять, максимум — вынести в приватный метод для переиспользования в `EventController`.

***

## 3. EventController: инструкция по изменениям

Сейчас `EventController` уже содержит:

- фильтр по `time_frame`;
- фильтр по `attendance_mode`;
- фильтр по радиусу по `event.venues`.


### 3.1. Расширить выборку venues у событий (при необходимости)

Если в `EventResource` вы хотите видеть `city_fias_id`, `regioniso`, `region_code`, нужно обновить `with(['event' => function ($q) { ... }])`:

```php
->with([
    'event' => function ($q) {
        $q->where('status', 'approved')
          ->with([
              'organizer.organizable',
              'categories',
              'venues' => function ($q2) {
                  $q2->select(
                      'venues.id',
                      'venues.address_raw',
                      'venues.coordinates',
                      'venues.fias_id',
                      'venues.city_fias_id',
                      'venues.regioniso',
                      'venues.region_code'
                  );
              },
          ]);
    },
])
```

(Если ресурсы уже выбирают все поля, это можно пропустить.)

### 3.2. Добавить фильтр по city_fias_id для событий

По аналогии с организациями, но через `event.venues`:

```php
// Filter events by city_fias_id (via event venues)
$cityFiasIds = $request->filled('city_fias_id')
    ? (array) $request->input('city_fias_id')
    : [];

if ($cityFiasIds !== []) {
    $cityFiasIds = array_filter(array_map('strval', $cityFiasIds));

    if ($cityFiasIds !== []) {
        $query->whereHas('event.venues', function ($q) use ($cityFiasIds) {
            $q->where(function ($q2) use ($cityFiasIds) {
                $q2->whereIn('city_fias_id', $cityFiasIds)
                   ->orWhere(function ($q3) use ($cityFiasIds) {
                       $q3->whereNull('city_fias_id')
                          ->where(function ($q4) use ($cityFiasIds) {
                              foreach ($cityFiasIds as $id) {
                                  $q4->orWhere('fias_id', 'LIKE', $id.'%');
                              }
                          });
                   });
            });
        });
    }
}
```


### 3.3. Добавить фильтр по региону для событий

Аналогично организациям:

```php
// Filter events by region (ISO or region_code)
if ($request->filled('regioniso') || $request->filled('region_code')) {
    $regionIso = $request->input('regioniso');
    $regionCode = $request->input('region_code');

    $query->whereHas('event.venues', function ($q) use ($regionIso, $regionCode) {
        $q->where(function ($q2) use ($regionIso, $regionCode) {
            if ($regionIso !== null) {
                $q2->orWhere('regioniso', $regionIso);
            }

            if ($regionCode !== null) {
                $q2->orWhere('region_code', $regionCode);
            }
        });
    });
}
```

Так же, как в `OrganizationController`, это закрывает кейс новых регионов.

### 3.4. Фильтр по радиусу — переиспользовать паттерн

Ваш текущий блок уже корректен по логике. Можем только вынести `ST_DWithin` в общий приватный метод (если хотите DRY), но для Cursor достаточно оставить как есть.

***

## 4. Как именно обрабатывать кейс «regioniso = null» в цепочке DaData → Navigator

Чтобы фильтры выше работали, нужно договориться о поведении enrichment‑скрипта (Python или PHP, который ходит в Дадату).

**Инструкция для Cursor по enrichment (отдельный файл, не контроллеры):**

1. При обработке ответа Дадаты для venue:
    - `venue.regioniso = data["region_iso_code"] ?? null;`
    - если `region_iso_code` == null:
        - взять один из стабильных идентификаторов региона:
            - `data["region_fias_id"]` (или `data["federal_district_fias_id"]` при необходимости);
        - записать его в `venue.region_code` (string).
2. Для старых регионов (где есть ISO):
    - `region_code` можно сделать равным `region_fias_id` для единообразия, но фильтрация будет в основном по `regioniso`.
3. На уровне API:
    - фронт, если получает от подсказок Дадаты `region_iso_code != null` — шлёт `regioniso`;
    - если `region_iso_code == null`, но есть `region_fias_id` — шлёт `region_code`.