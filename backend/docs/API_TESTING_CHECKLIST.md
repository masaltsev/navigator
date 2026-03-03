# Чек-лист ручных тестов API Navigator Core

## 1. Проверка миграций базы данных

### 1.1. Запуск миграций
- [ ] Выполнить `php artisan migrate` (или `php artisan migrate:fresh` для чистой БД)
- [ ] Проверить отсутствие ошибок в выводе
- [ ] Убедиться, что все таблицы созданы:
  - [ ] Справочники: `thematic_categories`, `services`, `organization_types`, `specialist_profiles`, `ownership_types`, `coverage_levels`, `event_categories`, `target_audience`
  - [ ] Основные сущности: `organizers`, `organizations`, `initiative_groups`, `individuals`
  - [ ] События: `events`, `event_instances`
  - [ ] Площадки: `venues`
  - [ ] Контент: `articles`
  - [ ] Pivot-таблицы: `organization_thematic_categories`, `organization_organization_types`, `organization_specialist_profiles`, `organization_services`, `event_event_categories`, `organization_venues`, `event_venues`
  - [ ] RBAC: `roles`, `role_user`, `user_organizer`

### 1.2. Проверка структуры таблиц
- [ ] Проверить наличие UUID первичных ключей в таблицах с UUID
- [ ] Проверить наличие PostGIS расширения и колонки `coordinates` в `venues`
- [ ] Проверить индексы на `inn`, `ogrn`, `status`, `works_with_elderly`
- [ ] Проверить foreign keys на справочники

### 1.3. Заполнение тестовыми данными (опционально)
- [ ] Создать seeders для справочников или заполнить вручную через SQL/Adminer
- [ ] Проверить, что справочники содержат данные (например, `organization_types.code = "82"`, `thematic_categories.code = "7"`)

---

## 2. Тестирование публичного API `/api/v1`

### 2.1. GET /api/v1/organizations (список организаций)

#### Базовый запрос
- [ ] Выполнить запрос без фильтров
- [ ] Проверить статус 200 OK
- [ ] Проверить структуру ответа: `data[]`, `meta` (пагинация)
- [ ] Проверить компактные поля в списке: `id`, `title`, `organization_types`, `venue`, `thematic_categories`, `specialist_profiles`, `services`

#### Фильтр по городу (city_fias_id)
- [ ] Выполнить запрос с `city_fias_id`
- [ ] Проверить, что возвращаются только организации с площадками в указанном городе

#### Фильтр по жизненным ситуациям (thematic_category_id[])
- [ ] Выполнить запрос с одним `thematic_category_id`
- [ ] Выполнить запрос с массивом `thematic_category_id[]`
- [ ] Проверить, что возвращаются только организации с указанными тематическими категориями

#### Фильтр по типам организаций (organization_type_id[])
- [ ] Выполнить запрос с одним или несколькими `organization_type_id[]`
- [ ] Проверить корректность фильтрации

#### Фильтр по услугам (service_id[])
- [ ] Выполнить запрос с `service_id[]`
- [ ] Проверить корректность фильтрации

#### Георадиусный фильтр (lat, lng, radius_km)
- [ ] Выполнить запрос с координатами и радиусом
- [ ] Проверить, что возвращаются только организации в указанном радиусе

#### Комбинированные фильтры
- [ ] Выполнить запрос с несколькими фильтрами одновременно
- [ ] Проверить корректность работы всех фильтров вместе

#### Фильтр works_with_elderly
- [ ] Выполнить запрос с `works_with_elderly=false`
- [ ] Проверить, что по умолчанию возвращаются только организации с `works_with_elderly=true`

#### Пагинация
- [ ] Проверить параметры `page` и `per_page`
- [ ] Проверить мета-информацию о пагинации

### 2.2. GET /api/v1/organizations/{id} (детальная карточка)

- [ ] Выполнить запрос с валидным UUID организации
- [ ] Проверить статус 200 OK
- [ ] Проверить полную структуру ответа:
  - [ ] Все поля организации (inn, ogrn, site_urls)
  - [ ] Массив `venues` с полной информацией
  - [ ] Массивы `thematic_categories`, `organization_types`, `specialist_profiles`, `services`
  - [ ] Связанные `events` (если загружены)
  - [ ] Связанные `articles` (если загружены)
- [ ] Проверить статус 404 для несуществующего UUID
- [ ] Проверить, что организации со статусом != `approved` не возвращаются

### 2.3. GET /api/v1/events (список событий)

#### Базовый запрос
- [ ] Выполнить запрос без фильтров
- [ ] Проверить, что возвращаются только будущие события (`start_datetime >= now`)
- [ ] Проверить статус `scheduled` у экземпляров событий

#### Фильтр по временному окну (time_frame)
- [ ] Проверить `time_frame=today`
- [ ] Проверить `time_frame=tomorrow`
- [ ] Проверить `time_frame=this_week`
- [ ] Проверить `time_frame=this_month`
- [ ] Проверить корректность дат в ответе

#### Фильтр по режиму участия (attendance_mode)
- [ ] Проверить `attendance_mode=offline`
- [ ] Проверить `attendance_mode=online`
- [ ] Проверить `attendance_mode=mixed`

#### Георадиусный фильтр
- [ ] Выполнить запрос с `lat`, `lng`, `radius_km`
- [ ] Проверить, что фильтр работает только для `offline` и `mixed` событий
- [ ] Проверить корректность расчета расстояния

#### Комбинированные фильтры
- [ ] Проверить комбинацию `time_frame` + `attendance_mode`
- [ ] Проверить комбинацию всех фильтров

---

## 3. Тестирование внутреннего API `/api/internal`

### 3.1. POST /api/internal/import/organizer

#### Создание организации (Organization)
- [ ] Выполнить запрос с полным JSON для `entity_type=Organization`
- [ ] Проверить статус 201 Created
- [ ] Проверить ответ: `organizer_id`, `entity_id`, `assigned_status`
- [ ] Проверить в БД:
  - [ ] Создана запись в `organizations`
  - [ ] Создана запись в `organizers` с правильным `organizable_type`
  - [ ] Созданы площадки в `venues` с координатами
  - [ ] Привязаны `thematic_categories`, `organization_types`, `specialist_profiles`, `services`
  - [ ] Статус соответствует State Machine логике

#### State Machine: Smart Publish (approved)
- [ ] Отправить запрос с `ai_confidence_score >= 0.85` и `works_with_elderly=true`
- [ ] Проверить, что `assigned_status = "approved"`

#### State Machine: Pending Review
- [ ] Отправить запрос с `ai_confidence_score < 0.85`
- [ ] Проверить, что `assigned_status = "pending_review"`

#### State Machine: Rejected
- [ ] Отправить запрос с `decision = "rejected"`
- [ ] Проверить, что `assigned_status = "rejected"`

#### Создание инициативной группы (InitiativeGroup)
- [ ] Выполнить запрос с `entity_type=InitiativeGroup`
- [ ] Проверить создание в `initiative_groups` и `organizers`

#### Валидация
- [ ] Проверить ошибки валидации при отсутствии обязательных полей
- [ ] Проверить ошибки при невалидных значениях enum
- [ ] Проверить ошибки при невалидных UUID

#### Обновление существующей организации
- [ ] Отправить запрос с тем же `inn` (если используется для уникальности)
- [ ] Проверить обновление данных, а не создание дубликата

### 3.2. POST /api/internal/import/event

#### Создание события
- [ ] Выполнить запрос с полным JSON для события
- [ ] Проверить статус 201 Created
- [ ] Проверить создание в `events`
- [ ] Проверить привязку к `organizer_id`
- [ ] Проверить денормализованное поле `organization_id` (если организатор - Organization)

#### Событие с RRule
- [ ] Отправить событие с `rrule_string` (например, `FREQ=WEEKLY;INTERVAL=1;BYDAY=TU,TH`)
- [ ] Проверить сохранение `rrule_string`
- [ ] Проверить, что материализация экземпляров будет выполнена (TODO в коде)

#### Привязка площадок
- [ ] Отправить событие с массивом `venues`
- [ ] Проверить создание/использование существующих площадок
- [ ] Проверить привязку через `event_venues`

#### Привязка категорий событий
- [ ] Отправить событие с `event_category_codes`
- [ ] Проверить привязку через `event_event_categories`

#### Валидация
- [ ] Проверить ошибки при несуществующем `organizer_id`
- [ ] Проверить ошибки при невалидных данных

### 3.3. POST /api/internal/import/batch

- [ ] Выполнить запрос с массивом `items`
- [ ] Проверить статус 202 Accepted
- [ ] Проверить ответ с `job_id` и `items_count`
- [ ] Проверить валидацию (максимум 100 элементов)

---

## 4. Дополнительные проверки

### 4.1. Производительность
- [ ] Проверить время ответа публичного API (должно быть < 500ms для списков)
- [ ] Проверить использование eager loading (отсутствие N+1 запросов)

### 4.2. Обработка ошибок
- [ ] Проверить обработку невалидных UUID
- [ ] Проверить обработку отсутствующих данных
- [ ] Проверить формат ошибок валидации

### 4.3. PostGIS координаты
- [ ] Проверить сохранение координат через PostGIS функции
- [ ] Проверить работу георадиусных фильтров
- [ ] Проверить извлечение координат в API Resources (если реализовано)

---

# Примеры curl-команд

## Публичный API

### 1. GET /api/v1/organizations (базовый запрос)

```bash
# Проверяет: получение списка одобренных организаций с пагинацией
curl -X GET "http://localhost/api/v1/organizations" \
  -H "Accept: application/json"
```

### 2. GET /api/v1/organizations с фильтром по городу и категории

```bash
# Проверяет: фильтрация по city_fias_id и thematic_category_id
curl -X GET "http://localhost/api/v1/organizations?city_fias_id=0c5b2444-70a0-4932-980c-b4dc0d3f02b5&thematic_category_id[]=7&thematic_category_id[]=12" \
  -H "Accept: application/json"
```

### 3. GET /api/v1/organizations с георадиусным фильтром

```bash
# Проверяет: фильтрация по радиусу от координат (Москва, радиус 5 км)
curl -X GET "http://localhost/api/v1/organizations?lat=55.7558&lng=37.6173&radius_km=5" \
  -H "Accept: application/json"
```

### 4. GET /api/v1/organizations с комбинированными фильтрами

```bash
# Проверяет: комбинация фильтров по услугам, категориям и георадиусу
curl -X GET "http://localhost/api/v1/organizations?service_id[]=81&service_id[]=83&thematic_category_id[]=7&lat=55.7558&lng=37.6173&radius_km=10&per_page=20" \
  -H "Accept: application/json"
```

### 5. GET /api/v1/organizations/{id} (детальная карточка)

```bash
# Проверяет: получение полной информации об организации
# Замените {uuid} на реальный UUID организации из БД
curl -X GET "http://localhost/api/v1/organizations/550e8400-e29b-41d4-a716-446655440000" \
  -H "Accept: application/json"
```

### 6. GET /api/v1/events с фильтром по времени и режиму участия

```bash
# Проверяет: фильтрация событий на эту неделю, только оффлайн
curl -X GET "http://localhost/api/v1/events?time_frame=this_week&attendance_mode=offline" \
  -H "Accept: application/json"
```

### 7. GET /api/v1/events с георадиусным фильтром

```bash
# Проверяет: оффлайн события в радиусе 3 км от координат
curl -X GET "http://localhost/api/v1/events?lat=55.7558&lng=37.6173&radius_km=3&attendance_mode=offline" \
  -H "Accept: application/json"
```

---

## Внутренний API

### 8. POST /api/internal/import/organizer (Organization с полными данными)

```bash
# Проверяет: создание организации через AI-пайплайн с полной структурой данных
curl -X POST "http://localhost/api/internal/import/organizer" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{
    "source_reference": "sfr_kld_12193_item_1",
    "entity_type": "Organization",
    "title": "Центр общения старшего поколения (Ленинградский район)",
    "description": "Организация досуга и социализации для граждан старшего поколения. Проведение культурно-массовых мероприятий, кружков по интересам, консультаций по социальным вопросам.",
    "inn": "3906012345",
    "ogrn": "1023900000123",
    "ai_metadata": {
      "decision": "accepted",
      "ai_explanation": "Учреждение из официального реестра СФР. Прямое указание на работу со старшим поколением. Регулярная деятельность подтверждена.",
      "ai_confidence_score": 0.98,
      "works_with_elderly": true,
      "ai_source_trace": [
        {
          "source_id": "550e8400-e29b-41d4-a716-446655440000",
          "source_item_id": "sfr_kld_12193_item_1",
          "source_url": "https://sfr.gov.ru/branches/kaliningrad/info/~0/12193",
          "extracted_at": "2026-02-17T10:00:00Z",
          "confidence": 0.98
        }
      ]
    },
    "classification": {
      "organization_type_codes": ["44"],
      "ownership_type_code": "164",
      "coverage_level_id": 2,
      "thematic_category_codes": ["82"],
      "service_codes": ["81", "70"]
    },
    "venues": [
      {
        "address_raw": "г. Калининград, ул. 9 Апреля, д.32а",
        "fias_id": "95a7ec9a-f3e0-4054-946e-52b82e4e1a1b",
        "geo_lat": 54.717,
        "geo_lon": 20.526,
        "is_headquarters": true
      }
    ]
  }'
```

### 9. POST /api/internal/import/organizer (Smart Publish - автоматическое одобрение)

```bash
# Проверяет: State Machine логику - автоматическое присвоение статуса "approved"
curl -X POST "http://localhost/api/internal/import/organizer" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{
    "source_reference": "dobro_ru_778899",
    "entity_type": "Organization",
    "title": "Центр серебряного добровольчества",
    "description": "Координация волонтерской деятельности граждан старшего возраста.",
    "inn": "7712345678",
    "ai_metadata": {
      "decision": "accepted",
      "ai_confidence_score": 0.94,
      "works_with_elderly": true,
      "ai_explanation": "Подтверждена деятельность в 2024 году на официальном сайте."
    },
    "classification": {
      "organization_type_codes": ["174"],
      "ownership_type_code": "162",
      "coverage_level_id": 2,
      "thematic_category_codes": ["7", "12"],
      "service_codes": ["81", "83"]
    },
    "venues": [
      {
        "address_raw": "г. Москва, ул. Тверская, д. 1",
        "fias_id": "0c5b2444-70a0-4932-980c-b4dc0d3f02b5",
        "geo_lat": 55.757,
        "geo_lon": 37.615,
        "is_headquarters": true
      }
    ]
  }'
```

### 10. POST /api/internal/import/organizer (Pending Review - низкая уверенность)

```bash
# Проверяет: State Machine логику - присвоение статуса "pending_review" при низкой уверенности
curl -X POST "http://localhost/api/internal/import/organizer" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{
    "source_reference": "vk_group_12345",
    "entity_type": "InitiativeGroup",
    "title": "Группа бабушек в парке Сокольники",
    "description": "Неформальная группа для общения и совместных прогулок.",
    "ai_metadata": {
      "decision": "accepted",
      "ai_confidence_score": 0.72,
      "works_with_elderly": true,
      "ai_explanation": "Группа в социальной сети, упоминания о пожилых людях неоднозначны."
    },
    "classification": {
      "problem_category_codes": ["82"]
    },
    "venues": [
      {
        "address_raw": "г. Москва, парк Сокольники",
        "geo_lat": 55.790,
        "geo_lon": 37.680,
        "is_headquarters": false
      }
    ]
  }'
```

### 11. POST /api/internal/import/organizer (Rejected)

```bash
# Проверяет: State Machine логику - отклонение при decision="rejected"
curl -X POST "http://localhost/api/internal/import/organizer" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{
    "source_reference": "test_rejected_org",
    "entity_type": "Organization",
    "title": "Детский развивающий центр",
    "description": "Центр для детей дошкольного возраста.",
    "ai_metadata": {
      "decision": "rejected",
      "ai_confidence_score": 0.95,
      "works_with_elderly": false,
      "ai_explanation": "Организация работает исключительно с детьми, не соответствует критериям."
    },
    "classification": {
      "organization_type_codes": ["34"]
    }
  }'
```

### 12. POST /api/internal/import/event (событие с RRule)

```bash
# Проверяет: создание события с повторяющимся расписанием (RRule)
# Предполагается, что organizer_id уже существует в БД
curl -X POST "http://localhost/api/internal/import/event" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{
    "source_reference": "event_vk_wall_12345",
    "organizer_id": "550e8400-e29b-41d4-a716-446655440000",
    "title": "Зарядка для пожилых людей",
    "description": "Еженедельные занятия утренней гимнастикой в парке. Подходит для всех уровней подготовки.",
    "attendance_mode": "offline",
    "rrule_string": "FREQ=WEEKLY;INTERVAL=1;BYDAY=TU,TH;COUNT=20",
    "ai_metadata": {
      "ai_confidence_score": 0.92,
      "ai_explanation": "Регулярное мероприятие, подтверждено в группе ВКонтакте.",
      "ai_source_trace": [
        {
          "source_id": "vk_group_silver_volunteers",
          "source_item_id": "wall_post_12345",
          "source_url": "https://vk.com/silver_volunteers?w=wall-12345_67890",
          "extracted_at": "2026-02-17T10:00:00Z"
        }
      ]
    },
    "classification": {
      "event_category_codes": ["lecture", "health"]
    },
    "venues": [
      {
        "address_raw": "г. Москва, парк Сокольники, центральная аллея",
        "geo_lat": 55.790,
        "geo_lon": 37.680
      }
    ]
  }'
```

### 13. POST /api/internal/import/event (онлайн-событие)

```bash
# Проверяет: создание онлайн-события с URL трансляции
curl -X POST "http://localhost/api/internal/import/event" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{
    "source_reference": "event_online_webinar_001",
    "organizer_id": "550e8400-e29b-41d4-a716-446655440000",
    "title": "Онлайн-лекция: Здоровое питание в пожилом возрасте",
    "description": "Врач-диетолог расскажет о принципах правильного питания для людей старшего возраста.",
    "attendance_mode": "online",
    "online_url": "https://zoom.us/j/123456789",
    "ai_metadata": {
      "ai_confidence_score": 0.88,
      "ai_explanation": "Онлайн-мероприятие, подтверждено на сайте организации."
    },
    "classification": {
      "event_category_codes": ["lecture", "health"]
    }
  }'
```

### 14. POST /api/internal/import/batch (пакетный импорт)

```bash
# Проверяет: пакетный импорт нескольких организаций
curl -X POST "http://localhost/api/internal/import/batch" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{
    "items": [
      {
        "source_reference": "batch_org_001",
        "entity_type": "Organization",
        "title": "Организация 1",
        "ai_metadata": {
          "decision": "accepted",
          "ai_confidence_score": 0.90,
          "works_with_elderly": true
        },
        "classification": {}
      },
      {
        "source_reference": "batch_org_002",
        "entity_type": "Organization",
        "title": "Организация 2",
        "ai_metadata": {
          "decision": "accepted",
          "ai_confidence_score": 0.87,
          "works_with_elderly": true
        },
        "classification": {}
      }
    ]
  }'
```

---

## Примечания к тестированию

1. **Базовый URL**: Замените `http://localhost` на актуальный URL вашего приложения (например, `https://navigator.test` для Laravel Herd).

2. **UUID для тестов**: В примерах используются placeholder UUID. Для реального тестирования:
   - Сначала создайте организацию через `/api/internal/import/organizer`
   - Используйте полученный `organizer_id` в запросах событий

3. **Справочники**: Убедитесь, что справочники заполнены данными:
   - `organization_types` с кодами "44", "174" и т.д.
   - `thematic_categories` с кодами "7", "12", "82"
   - `services` с кодами "70", "81", "83"
   - `event_categories` со slug "lecture", "health"

4. **Аутентификация**: Внутренние эндпоинты требуют аутентификации. Добавьте заголовок авторизации, когда она будет настроена:
   ```bash
   -H "Authorization: Bearer YOUR_API_TOKEN"
   ```

5. **Проверка ответов**: Используйте `jq` для форматирования JSON ответов:
   ```bash
   curl ... | jq .
   ```
