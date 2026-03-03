# Cursor Script: Обогащение venues через DaData

Ты работаешь в этом репозитории как Senior Laravel‑разработчик.

Важные документы:

- `/Users/masaltsev/Documents/dev/navigator/docs/Navigator_Core_Model_and_API.md` — доменная модель Navigator Core (структура `venues`, использование `fias_id` и `coordinates` в API).
- `/Users/masaltsev/Documents/dev/navigator/backend/docs/address_enrichment_via_dadata.md` — подробное описание текущих проблем с `venues` и требований к обогащению через DaData (обязательно прочитай полностью перед началом работы).

Цель: реализовать безопасный, перезапускаемый механизм обогащения таблицы `venues` через API DaData, чтобы:

- заполнить `fias_id` (уровень населённого пункта),
- при необходимости — `kladr_id`, `region_iso`, `coordinates`,
- оживить фильтр `GET /api/v1/organizations?city_fias_id=...`.

Важно: это **не AI‑задача**, а сервисный ETL‑шаг. Никаких LLM не используется, только DaData.
При этом в дальнейшем сервис может стать частью AI-пайплайна, напиши его так, чтобы можно было легко переписать под python.

---

## Шаг 1. Прочитать спецификацию адресов

1. Прочитай [address_enrichment_via_dadata.md](./address_enrichment_via_dadata.md) и коротко зафиксируй для себя, что:

   - `venues.address_raw` — исходный строковый адрес (из WP).
   - `venues.fias_id` — **FIAS населённого пункта** (город/село) и используется в фильтре `city_fias_id` в API.
   - `venues.coordinates` — точное гео (Point, SRID 4326), используется для поиска по радиусу.
   - сейчас `fias_id` почти везде NULL, поэтому фильтр по городу не работает.

2. Обрати внимание на разделы:

   - «Разделение ролей: fias_id vs coordinates»
   - «Что должен делать скрипт обогащения через DaData»
   - «Рекомендуемые шаги при реализации»

---

## Шаг 2. Конфигурация доступа к DaData

1. Предусмотри конфигурацию для DaData в `.env` и `config/services.php`:

   - В `.env` (примеры переменных, не заполняй реальные ключи):

     ```env
     DADATA_API_KEY=your_api_key_here
     DADATA_SECRET_KEY=your_secret_here
     DADATA_BASE_URL=https://suggestions.dadata.ru/suggestions/api/4_1/rs
     ```

   - В `config/services.php`:

     ```php
     'dadata' => [
         'api_key'    => env('DADATA_API_KEY'),
         'secret_key' => env('DADATA_SECRET_KEY'),
         'base_url'   => env('DADATA_BASE_URL', 'https://suggestions.dadata.ru/suggestions/api/4_1/rs'),
     ],
     ```

2. Реализуй отдельный сервис‑клиент для DaData, например `App\Services\Dadata\DadataClient`:

   - метод `suggestAddress(string $query): ?array` — вызов метода DaData по адресу (адрес → стандартные данные, включая FIAS, координаты и т.д.);
   - (опционально) метод `reverseGeocode(float $lat, float $lon): ?array`, если ты добавишь обогащение по координатам.

   Используй `Http` (Laravel HTTP client) и учитывай заголовки DaData (`Authorization`, `X-Secret` и т.п.).

---

## Шаг 3. Сервис обогащения площадок

Создай сервис, инкапсулирующий всю логику работы с DaData и venues, например `App\Services\VenueAddressEnricher`.

Требования:

1. Интерфейс сервиса:

   ```php
   class VenueAddressEnricher
   {
       public function enrichByAddress(Venue $venue): EnrichmentResult;
       public function enrichByCoordinates(Venue $venue): EnrichmentResult; // опционально
   }
```

Где `EnrichmentResult` — простой DTO/класс/массив с полями:

- новый `fias_id` (или null),
- новый `kladr_id` (или null),
- новый `region_iso` (или null),
- новые координаты (`lat`, `lon`) — если решишь их обновлять,
- флаг/код статуса (`success`, `not_found`, `error`),
- текст ошибки (если есть).

2. В `enrichByAddress`:
    - Используй `venue.address_raw` для запроса к DaData.
    - Из ответа DaData выбирай:
        - FIAS **населённого пункта** (НЕ дома). В зависимости от формата ответа DaData это может быть:
            - `data.city_fias_id` или `data.settlement_fias_id` (если есть),
            - или другой подходящий уровень, который соответствует городу/НП.
        - Координаты `data.geo_lat`, `data.geo_lon` (если у площадки сейчас они пустые или ты решил их обновлять).
        - При необходимости — `kladr_id`, код региона.
    - Не зашивай конкретную структуру ответа жёстко — добавь минимум проверок на наличие полей и graceful fallback.
3. В `enrichByCoordinates` (опционально):
    - Если ты будешь использовать reverse‑geocoding DaData:
        - Считывай `venue.coordinates` (lat/lon),
        - вызывай соответствующий метод DaData,
        - извлекай FIAS НП и другие поля по аналогии с `enrichByAddress`.

---

## Шаг 4. Консольная команда `venues:enrich-addresses`

Создай Laravel‑команду, например:

```bash
php artisan make:command EnrichVenueAddresses
# имя команды внутри: venues:enrich-addresses
```

Требования к команде:

1. Аргументы/опции:
    - `--limit=` (int) — максимальное количество venues за один прогон (по умолчанию, например, 100 или 1000).
    - `--force` — перезаписывать `fias_id` даже если он уже заполнен.
    - `--by-geo` — включить второй режим: обогащение площадок, у которых нет `address_raw`, но есть `coordinates`.
    - `--dry-run` — не записывать изменения в БД, только логировать предполагаемые обновления.
2. Логика отбора записей:

По умолчанию (без `--by-geo`):

```sql
SELECT * FROM venues
WHERE fias_id IS NULL
  AND address_raw IS NOT NULL
ORDER BY id
LIMIT :limit;
```

Если передан `--force`, то можно убирать условие `fias_id IS NULL` и обновлять все подряд.

Если передан `--by-geo`, отдельный проход:

```sql
SELECT * FROM venues
WHERE fias_id IS NULL
  AND address_raw IS NULL
  AND coordinates IS NOT NULL
ORDER BY id
LIMIT :limit;
```

Важно: оба режима должны быть независимы; по умолчанию — только по адресу.
3. Обработка:
    - для каждой выбранной площадки:
        - если работаем по адресу:
            - вызвать `VenueAddressEnricher::enrichByAddress($venue)`;
        - если `--by-geo` и `address_raw` пустой:
            - вызвать `enrichByCoordinates($venue)` (если реализуешь) или просто логировать как «пока пропускаем».
    - если `--dry-run`:
        - **не** сохранять в БД, только выводить в консоль/лог, какие значения будут установлены (`id`, `old_fias`, `new_fias`, координаты и т.п.).
    - без `--dry-run`:
        - обновить поля `fias_id`, `kladr_id`, `region_iso`, `coordinates` (если решил обновлять),
        - сохранить модель,
        - аккуратно логировать результаты (успех/ошибка).
4. Обязательно:
    - учти лимиты DaData: сделай небольшую задержку/пакетную отправку или задай максимальное количество запросов в секунду;
    - оборачивай вызовы DaData в try/catch, логируй таймауты и ошибки, но не падай на первой неудачной площадке;
    - в конце команды выведи простую статистику: сколько venues обработано, сколько обновлено, сколько ошибок/`not_found`.

---

## Шаг 5. Безопасность и тестирование

1. Не добавляй в репозиторий реальные ключи DaData. Всё через `.env`. В коде вместо реальных значений используй `env('DADATA_API_KEY')` и т.п.
2. Добавь хотя бы простой unit/feature‑тест для сервиса `VenueAddressEnricher` с моками HTTP‑ответа DaData (чтобы убедиться, что:
    - из типичного ответа берётся правильный FIAS НП,
    - корректно формируется результат для `Venue`).
3. После реализации:
    - покажи diff изменённых файлов:
        - `config/services.php`,
        - сервисы DaData/Enricher,
        - файл команды,
        - любые вспомогательные классы.
    - Не вызывай команду массово (`php artisan venues:enrich-addresses`) автоматически. Мы будем запускать её вручную после просмотра кода.