# План реализации фильтрации по новым регионам (ЛНР/ДНР/Херсон/Запорожье)

## Цель
Добавить поддержку фильтрации по регионам без ISO-кода (ЛНР, ДНР, Херсонская, Запорожская области) через поле `region_code`, которое будет хранить идентификатор региона из DaData (например, `region_fias_id`).

## Пошаговый план

### Шаг 1: Миграция — добавить поле `region_code` в таблицу `venues`
**Файл:** `database/migrations/YYYY_MM_DD_HHMMSS_add_region_code_to_venues_table.php`

**Действия:**
- Добавить колонку `region_code` (string, nullable, indexed) в таблицу `venues`
- Разместить после `region_iso`

**Код:**
```php
Schema::table('venues', function (Blueprint $table) {
    $table->string('region_code')->nullable()->after('region_iso')->index();
});
```

---

### Шаг 2: Обновить `EnrichmentResult` — добавить поле `regionCode`
**Файл:** `app/Services/VenueAddressEnricher/EnrichmentResult.php`

**Действия:**
- Добавить `public readonly ?string $regionCode = null` в конструктор
- Добавить параметр `regionCode` в метод `success()`
- Передавать `regionCode` при создании результата

---

### Шаг 3: Обновить `VenueAddressEnricher` — извлекать `region_code` из DaData
**Файл:** `app/Services/VenueAddressEnricher/VenueAddressEnricher.php`

**Действия:**
- В методе `mapDataToResult()` добавить логику:
  - Если `region_iso_code` == null → взять `region_fias_id` и сохранить в `regionCode`
  - Если `region_iso_code` != null → `regionCode` можно оставить null или также сохранить `region_fias_id` для единообразия
- Создать метод `pickRegionCode(array $data): ?string` для извлечения `region_fias_id` когда `region_iso_code` отсутствует
- Передавать `regionCode` в `EnrichmentResult::success()`

---

### Шаг 4: Обновить команду `EnrichVenueAddresses` — сохранять `region_code`
**Файл:** `app/Console/Commands/EnrichVenueAddresses.php`

**Действия:**
- В методе `enrichVenue()` добавить сохранение `region_code`:
  ```php
  $venue->region_code = $result->regionCode;
  ```
- Обновить логику выборки для обогащения только venues с `region_iso = null` (новые регионы):
  - Добавить опцию `--new-regions-only` или автоматически фильтровать по `region_iso IS NULL`
  - Обновить `whereVenueIncomplete()` чтобы учитывать `region_code` (но не требовать его для "полноты")

---

### Шаг 5: Обновить `OrganizationController` — расширить выборку venues и добавить фильтр по региону
**Файл:** `app/Http/Controllers/Api/V1/OrganizationController.php`

**Действия:**
- **5.1.** Расширить выборку venues в `index()`:
  ```php
  'venues' => function ($q) {
      $q->select(
          'venues.id',
          'venues.address_raw',
          'venues.coordinates',
          'venues.fias_id',
          'venues.city_fias_id',
          'venues.region_iso',
          'venues.region_code'
      )
      ->orderBy('organization_venues.is_headquarters', 'desc')
      ->limit(1);
  }
  ```

- **5.2.** Добавить фильтр по региону (после фильтра по `city_fias_id`):
  ```php
  // Filter by region (ISO or region_code for new regions)
  if ($request->filled('region_iso') || $request->filled('region_code')) {
      $regionIso = $request->input('region_iso');
      $regionCode = $request->input('region_code');
      
      $query->whereHas('venues', function ($q) use ($regionIso, $regionCode) {
          $q->where(function ($q2) use ($regionIso, $regionCode) {
              if ($regionIso !== null) {
                  $q2->orWhere('region_iso', $regionIso);
              }
              
              if ($regionCode !== null) {
                  $q2->orWhere('region_code', $regionCode);
              }
          });
      });
  }
  ```

- **5.3.** Обновить PHPDoc комментарий метода `index()` с описанием новых параметров

---

### Шаг 6: Обновить `EventController` — добавить фильтры по городу и региону
**Файл:** `app/Http/Controllers/Api/V1/EventController.php`

**Действия:**
- **6.1.** Расширить выборку venues в `with(['event' => ...])`:
  ```php
  'venues' => function ($q2) {
      $q2->select(
          'venues.id',
          'venues.address_raw',
          'venues.coordinates',
          'venues.fias_id',
          'venues.city_fias_id',
          'venues.region_iso',
          'venues.region_code'
      );
  }
  ```

- **6.2.** Добавить фильтр по `city_fias_id` (после фильтра по `attendance_mode`, перед фильтром по радиусу):
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

- **6.3.** Добавить фильтр по региону (после фильтра по `city_fias_id`):
  ```php
  // Filter events by region (ISO or region_code)
  if ($request->filled('region_iso') || $request->filled('region_code')) {
      $regionIso = $request->input('region_iso');
      $regionCode = $request->input('region_code');
      
      $query->whereHas('event.venues', function ($q) use ($regionIso, $regionCode) {
          $q->where(function ($q2) use ($regionIso, $regionCode) {
              if ($regionIso !== null) {
                  $q2->orWhere('region_iso', $regionIso);
              }
              
              if ($regionCode !== null) {
                  $q2->orWhere('region_code', $regionCode);
              }
          });
      });
  }
  ```

- **6.4.** Обновить PHPDoc комментарий метода `index()` с описанием новых параметров

---

### Шаг 7: Обновить команду обогащения — обогащать только venues с `region_iso = null`
**Файл:** `app/Console/Commands/EnrichVenueAddresses.php`

**Действия:**
- Добавить опцию `--new-regions-only` для обогащения только venues с `region_iso IS NULL`
- Или автоматически фильтровать по `region_iso IS NULL` при обогащении (если не указан `--force`)
- Обновить логику выборки: когда используется `--new-regions-only` или по умолчанию для новых регионов, выбирать только venues где `region_iso IS NULL` и есть `address_raw`

---

### Шаг 8: Тестирование
**Действия:**
- Проверить миграцию (запустить и откатить)
- Проверить обогащение: запустить на тестовых venues с `region_iso = null`
- Проверить API фильтры:
  - `GET /api/v1/organizations?region_iso=RU-MOW`
  - `GET /api/v1/organizations?region_code=<fias_id>` (для новых регионов)
  - `GET /api/v1/events?city_fias_id=...`
  - `GET /api/v1/events?region_iso=...` или `region_code=...`

---

## Важные замечания

1. **DaData как источник истины:** Для Крыма, Байконура, Севастополя используем коды из DaData (UA-43, KZ-BAY, UA-40), не меняем их на российские.

2. **Обогащение только новых регионов:** Команда обогащения должна обрабатывать только venues с `region_iso = null` (ЛНР, ДНР, Херсонская, Запорожская области). Остальные venues не трогаем.

3. **Обратная совместимость:** Фильтр по `region_iso` продолжает работать для существующих регионов. Новый параметр `region_code` используется только для регионов без ISO-кода.

4. **Поле `region_code`:** Хранит `region_fias_id` из DaData когда `region_iso_code` отсутствует. Это позволяет фильтровать по идентификатору региона даже без ISO-кода.
