# Описание тестов API Navigator Core

**Дата:** 2026-02-27  
**Git commit:** 0b951e1  
**Область:** тесты API бэкенда — `backend/tests/Feature/Api/`  
**Источник истины:** [docs/Navigator_Core_Model_and_API.md](../../../docs/Navigator_Core_Model_and_API.md)

Документ перечисляет все автоматические тесты API (Pest, Feature) и что каждый из них проверяет. Маршруты и контракты описаны в `backend/routes/api.php` и в архитектурном документе.

---

## 1. Публичный API v1

Префикс: `/api/v1`. Эндпоинты без аутентификации.

### 1.1. OrganizationsTest (`tests/Feature/Api/V1/OrganizationsTest.php`)

| Тест | Что проверяет |
|------|----------------|
| GET /api/v1/organizations returns successful response with pagination | Успешный ответ, структура `data[*]`: id, title, organization_types, thematic_categories, specialist_profiles, services; структура `meta`: current_page, per_page, total; при наличии venue у первого элемента — ключи id, address |
| GET /api/v1/organizations filters by city_fias_id | Запрос с `city_fias_id` из venue с заполненным fias_id; 200; при отсутствии подходящих организаций — skip |
| GET /api/v1/organizations filters by thematic_category_id | Запрос с одним thematic_category_id; 200; все вернувшиеся организации содержат эту категорию в thematic_categories |
| GET /api/v1/organizations filters by multiple thematic_category_id | Запрос с двумя thematic_category_id[]; 200 |
| GET /api/v1/organizations filters by organization_type_id | Запрос с organization_type_id[]; 200; при отсутствии типов в БД — skip |
| GET /api/v1/organizations filters by service_id | Запрос с service_id[]; 200; при отсутствии услуг — skip |
| GET /api/v1/organizations filters by geo-radius (lat, lng, radius_km) | Запрос с lat, lng, radius_km (Москва, 50 км); 200; при отсутствии организаций с координатами — skip |
| GET /api/v1/organizations filters by works_with_elderly=false | Запрос с works_with_elderly=false; 200 |
| GET /api/v1/organizations filters by regioniso | Запрос с regioniso из первого venue с заполненным region_iso; 200; при отсутствии таких venue — skip |
| GET /api/v1/organizations filters by region_code | Запрос с region_code из первого venue с заполненным region_code; 200; при отсутствии — skip |
| GET /api/v1/organizations index response includes type and required keys | per_page=1; у первого элемента наличие ключей id, type, title, organization_types, thematic_categories, specialist_profiles, services; type === 'Organization'; при venue — id, address; при пустой БД — skip |
| GET /api/v1/organizations pagination works | page=1, per_page=5; meta.per_page=5, meta.current_page=1; ровно 5 элементов в data |
| GET /api/v1/organizations/{id} returns full organization details | Детальная карточка: структура data (id, title, inn, ogrn, site_urls, ownership_type, coverage_level, venues[*] с id, address, fias_id, is_headquarters, thematic_categories, organization_types, specialist_profiles, services); наличие ключей events, articles; ownership_type и coverage_level — массивы; при отсутствии approved-организаций — skip |
| GET /api/v1/organizations/{id} returns 404 for non-existent UUID | UUID 00000000-...; 404 |
| GET /api/v1/organizations/{id} does not return non-approved organizations | Запрос по id организации со статусом != approved; 404; при отсутствии таких — skip |
| GET /api/v1/organizations combines multiple filters | Комбинация thematic_category_id[] + service_id[] + per_page=10; 200; при отсутствии категории или услуги — skip |

### 1.2. EventsTest (`tests/Feature/Api/V1/EventsTest.php`)

| Тест | Что проверяет |
|------|----------------|
| GET /api/v1/events returns successful response | Успешный ответ; структура data[*]: id, title |
| GET /api/v1/events returns full event structure when data present | per_page=1; структура data, meta (current_page, per_page, total); при непустом data у первого элемента: id, event_id, title, attendance_mode, start_datetime, end_datetime, status; при venue — id, address; при categories — массив; при organizer — id, type, name |
| GET /api/v1/events pagination works | per_page=3; meta.per_page=3; в data не более 3 элементов |
| GET /api/v1/events filters by time_frame=today | time_frame=today; 200 |
| GET /api/v1/events filters by time_frame=tomorrow | time_frame=tomorrow; 200 |
| GET /api/v1/events filters by time_frame=this_week | time_frame=this_week; 200 |
| GET /api/v1/events filters by time_frame=this_month | time_frame=this_month; 200 |
| GET /api/v1/events filters by attendance_mode=offline | attendance_mode=offline; 200 |
| GET /api/v1/events filters by attendance_mode=online | attendance_mode=online; 200 |
| GET /api/v1/events filters by attendance_mode=mixed | attendance_mode=mixed; 200 |
| GET /api/v1/events combines time_frame and attendance_mode filters | time_frame=this_week и attendance_mode=offline; 200 |
| GET /api/v1/events filters by geo-radius for offline events | lat, lng, radius_km, attendance_mode=offline; 200 |
| GET /api/v1/events filters by city_fias_id | city_fias_id из venue с fias_id; 200; при отсутствии таких venue — skip |
| GET /api/v1/events filters by regioniso | regioniso из venue с region_iso; 200; при отсутствии — skip |
| GET /api/v1/events filters by region_code | region_code из venue с region_code; 200; при отсутствии — skip |

---

## 2. Внутренний API (internal)

Префикс: `/api/internal`. Все запросы требуют заголовок `Authorization: Bearer <token>`. В тестах используется `config(['internal.api_token' => 'test-token'])` и заголовок `Bearer test-token`.

### 2.1. ImportTest (`tests/Feature/Api/Internal/ImportTest.php`)

| Тест | Что проверяет |
|------|----------------|
| POST /api/internal/import/organizer creates Organization with full data | Создание организации с source_reference, entity_type=Organization, title, description, inn, ogrn, ai_metadata (decision, ai_confidence_score, works_with_elderly), classification (organization_type_codes, ownership_type_code, thematic_category_codes), venues (address_raw, geo_lat, geo_lon, is_headquarters); 201; структура ответа: organizer_id, entity_id, assigned_status; в БД созданы Organization и Organizer, organizable_type=Organization, source_reference сохранён |
| POST /api/internal/import/organizer assigns approved status for high confidence | Импорт с ai_confidence_score=0.90, works_with_elderly=true; assigned_status === 'approved' |
| POST /api/internal/import/organizer assigns pending_review for low confidence | Импорт с ai_confidence_score=0.70; assigned_status === 'pending_review' |
| POST /api/internal/import/organizer validates required fields | Пустой body; 422; ошибки валидации по source_reference, entity_type, title |
| deduplication by source_reference updates existing organization | Два запроса с одним source_reference; вторая организация не создаётся, обновляется существующая |
| deduplication by inn when source_reference differs | Дедупликация по inn при разном source_reference (логика обновления по ИНН) |
| organizations without inn get separate records | Организации без ИНН создаются как отдельные записи |
| vk_group_url is converted to vk_group_id | Преобразование URL группы VK в vk_group_id при импорте |
| short_title is persisted on import | Сохранение short_title при импорте |
| venues receive geo fields from Harvester | Площадки получают region_iso, region_code и др. поля от Harvester |
| POST /api/internal/import/event creates event with deduplication | Создание события через import/event; дедупликация по source_reference |
| POST /api/internal/import/batch accepts batch import | Пакетный импорт через import/batch; принятие запроса и обработка |
| GET /api/internal/organizers lookup by source_reference | Поиск организатора по source_reference; корректный ответ |
| GET /api/internal/organizers returns 404 for unknown reference | Неизвестный source_reference; 404 |
| GET /api/internal/organizers lookup by source_id | Поиск по source_id |
| GET /api/internal/organizers lookup by inn | Поиск по inn |
| GET /api/internal/organizers returns 401 without token | Запрос без токена; 401 |
| POST /api/internal/import/organizer assigns rejected status when decision is rejected | ai_metadata.decision=rejected; assigned_status === 'rejected' |
| GET /api/internal/organizations/without-sources returns paginated list | Список организаций без источников; пагинация |
| GET /api/internal/organizations/without-sources caps per_page at 500 | Ограничение per_page максимум 500 |
| GET /api/internal/organizations/without-sources items have required fields | Элементы списка содержат обязательные поля (org_id, organizer_id, title и т.д.) |

### 2.2. SourceTest (`tests/Feature/Api/Internal/SourceTest.php`)

Вспомогательная функция создаёт организацию и организатора через POST /api/internal/import/organizer; заголовки: `Authorization: Bearer test-token`.

| Тест | Что проверяет |
|------|----------------|
| GET /api/internal/sources/{id} returns one source | Получение одного источника по id; 200; data.id, data.base_url, data.organizer_id, data.kind |
| GET /api/internal/sources/{id} returns 404 for unknown id | Неизвестный UUID; 404 |
| GET /api/internal/sources/due returns sources due for crawling | Список источников к обходу (due); структура data[*]: id, base_url, organizer_id, existing_entity_id, source_item_id, kind; созданный источник с last_crawled_at=null присутствует в ответе |
| GET /api/internal/sources requires organizer_id | Запрос без organizer_id; 422; ошибка валидации organizer_id |
| GET /api/internal/sources returns list for organizer | Список источников по organizer_id; структура data[*]: id, name, kind, base_url, last_status, is_active; один созданный источник, base_url совпадает |
| GET /api/internal/sources filters by kind | Фильтр kind=vk_group; один источник с kind=vk_group |
| POST /api/internal/sources accepts aggregator kind registry_fpg | Создание источника с kind=registry_fpg; 201; kind, status=created |
| POST /api/internal/sources creates source and returns 201 | Создание с organizer_id, base_url, kind=org_website; 201; status=created, organizer_id, base_url, kind, source_id; в БД источник с тем же base_url и kind |
| POST /api/internal/sources syncs site_urls when kind is org_website | При kind=org_website URL добавляется в organization.site_urls |
| POST /api/internal/sources returns exists when duplicate organizer_id and base_url | Повторный POST с тем же organizer_id и base_url; 200; status=exists, source_id первого создания |
| PATCH /api/internal/sources/{id} updates source | Обновление last_status, name; 200; status=updated; в БД значения обновлены |
| PATCH /api/internal/sources/{id} syncs site_urls when base_url changes for org_website | Смена base_url у источника org_website; в organization.site_urls старый URL удалён, новый добавлен |
| PATCH /api/internal/sources/{id} returns 409 when new base_url conflicts with another source | Смена base_url на уже существующий у другого источника того же организатора; 409; status=conflict |
| PATCH /api/internal/sources/{id} accepts last_crawled_at | Обновление last_crawled_at и last_status; 200; в БД last_crawled_at заполнен |
| PATCH /api/internal/sources/{id} returns 404 for unknown id | PATCH по неизвестному UUID; 404 |
| GET /api/internal/sources returns 401 without token | GET без заголовка Authorization; 401 |
| POST /api/internal/sources validates required fields | Пустой body; 422; ошибки по organizer_id, base_url, kind |

---

## 3. Запуск тестов

```bash
cd backend
php artisan test --compact tests/Feature/Api/
```

Отдельно публичный v1:

```bash
php artisan test --compact tests/Feature/Api/V1/
```

Отдельно внутренний API:

```bash
php artisan test --compact tests/Feature/Api/Internal/
```

---

## 4. Связанные документы

- [API_TESTING_CHECKLIST.md](../API_TESTING_CHECKLIST.md) — чек-лист ручной проверки API
- [internal_api_authentication.md](../internal_api_authentication.md) — аутентификация внутреннего API
- [docs/Navigator_Core_Model_and_API.md](../../../docs/Navigator_Core_Model_and_API.md) — контракты и модель данных
