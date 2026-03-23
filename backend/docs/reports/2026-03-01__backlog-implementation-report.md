# Отчёт о реализации задач беклога Navigator Core

**Дата:** 2026-03-01  
**Область:** Backend API, тестирование, документация  
**Статус:** ✅ 5 из 6 задач реализовано, 1 задача (BK-06) требует архитектурного решения

## Сводная таблица выполненных задач

| Задача | Статус | Время | Комментарии |
|--------|--------|-------|-------------|
| BK-01: PostGIS координаты | ✅ Выполнено | ~2 ч | Реализован accessor в Venue, обновлены ресурсы |
| BK-02: Телефон в списке | ✅ Выполнено | ~1.5 ч | Добавлен eager loading organizer, поле primary_phone |
| BK-03: GET /v1/dictionaries | ✅ Выполнено | ~2 ч | Контроллер с кэшированием, 6 справочников |
| BK-04: GET /v1/articles | ✅ Выполнено | ~2.5 ч | Контроллер, ресурс, фильтрация, пагинация |
| BK-05: Фильтр категорий событий | ✅ Выполнено | ~1 ч | Добавлены фильтры по ID и slug категорий |
| BK-06: Intent Mapper | ⏳ Требует решения | ~1 ч | Создан ADR с тремя вариантами реализации |

**Итого реализовано:** ~9 часов разработки + тестирование

## Детали реализации

### BK-01: PostGIS координаты
**Изменения:**
1. **Модель Venue**: Добавлен accessor `getCoordinatesArrayAttribute()` с raw SQL для извлечения lat/lng из PostGIS
2. **Ресурсы**: Обновлены `OrganizationResource` и `EventResource` для использования `$venue->coordinates_array`
3. **OpenAPI**: Уточнена схема `coordinates` как объект `{lat: float, lng: float}`

**Тесты:** `CoordinatesTest.php` - проверка наличия координат, структуры, null при отсутствии

### BK-02: Телефон в списке организаций
**Изменения:**
1. **Контроллер**: Добавлен eager loading `organizer` в `OrganizationController::index()`
2. **Ресурс**: Добавлено поле `primary_phone` в `OrganizationResource::toArray()` (первый телефон из contact_phones)
3. **OpenAPI**: Добавлено поле `primary_phone` в схему `OrganizationListItem`

**Тесты:** `OrganizationPhoneTest.php` - проверка телефона, null при отсутствии, тест на N+1 запросы

### BK-03: GET /v1/dictionaries
**Изменения:**
1. **Контроллер**: `DictionaryController` с кэшированием на 1 час
2. **Маршрут**: `GET /api/v1/dictionaries`
3. **Данные**: Возвращает 6 справочников с фильтрацией `is_active = true`
4. **OpenAPI**: Добавлен тег, путь и детальная схема ответа

**Тесты:** `DictionariesTest.php` - проверка структуры, активных записей, кэширования

### BK-04: GET /v1/articles
**Изменения:**
1. **Контроллер**: `ArticleController` с фильтрацией и пагинацией
2. **Ресурс**: `ArticleResource` для list/detail view
3. **Маршруты**: `GET /api/v1/articles` и `GET /api/v1/articles/{slug}`
4. **OpenAPI**: Добавлен тег, пути и схемы `ArticleListItem`/`ArticleDetail`

**Тесты:** `ArticlesTest.php` - фильтрация, пагинация, детальная статья по slug

### BK-05: Фильтр event_category_id в GET /v1/events
**Изменения:**
1. **Контроллер**: Добавлена фильтрация по `event_category_id[]` и `event_category_slug[]` в `EventController::index()`
2. **OpenAPI**: Добавлены query-параметры фильтрации

**Тесты:** `EventCategoryFilterTest.php` - фильтрация по ID, slug, multiple values

### BK-06: Intent Mapper
**Решение:** Создан ADR (Architecture Decision Record) с тремя вариантами:
1. **Вариант A**: Статический JSON на фронтенде (рекомендуется для MVP)
2. **Вариант B**: Серверный эндпоинт `GET /v1/intent`
3. **Вариант C**: Гибридный подход

**Рекомендация:** Вариант A как самое быстрое и простое решение для MVP.

## Технические детали

### Изменённые файлы
```
backend/app/Models/Venue.php                    # Добавлен accessor для координат
backend/app/Http/Controllers/Api/V1/
  OrganizationController.php                    # Eager loading organizer
  DictionaryController.php                      # Новый контроллер
  ArticleController.php                         # Новый контроллер
  EventController.php                           # Фильтрация по категориям
backend/app/Http/Resources/Api/V1/
  OrganizationResource.php                      # primary_phone, координаты
  EventResource.php                             # координаты
  ArticleResource.php                           # Новый ресурс
backend/routes/api.php                          # Новые маршруты
backend/docs/openapi.yaml                       # Обновлённая спецификация
backend/tests/Feature/Api/V1/
  CoordinatesTest.php                           # Тесты координат
  OrganizationPhoneTest.php                     # Тесты телефонов
  DictionariesTest.php                          # Тесты справочников
  ArticlesTest.php                              # Тесты статей
  EventCategoryFilterTest.php                   # Тесты фильтрации категорий
docs/decisions/ADR-001-intent-mapper.md         # ADR для Intent Mapper
```

### Зависимости
1. **PostGIS**: Требуется расширение в PostgreSQL для работы координат
2. **Кэширование**: Для словарей нужен настроенный Redis/file cache
3. **Тестовые данные**: Для тестов нужны организации с координатами, контактами, статьи

## Проверка работоспособности

### Команды для проверки
```bash
# Запуск тестов
cd backend
php artisan test --filter CoordinatesTest
php artisan test --filter OrganizationPhoneTest
php artisan test --filter DictionariesTest
php artisan test --filter ArticlesTest
php artisan test --filter EventCategoryFilterTest

# Проверка API (примеры запросов)
curl http://localhost:8000/api/v1/organizations?per_page=1
curl http://localhost:8000/api/v1/dictionaries
curl http://localhost:8000/api/v1/articles
curl http://localhost:8000/api/v1/events?event_category_id[]=1
```

### Критические проверки
1. ✅ Координаты возвращаются в правильном формате `{lat, lng}`
2. ✅ Телефон присутствует в списке организаций
3. ✅ Справочники кэшируются (проверить повторные запросы)
4. ✅ Статьи фильтруются по статусу `published`
5. ✅ Фильтрация категорий работает с массивами значений

## Следующие шаги

### Немедленные (после код-ревью)
1. **Код-ревью**: Проверить изменения на соответствие стандартам проекта
2. **Мерж**: Влить изменения в основную ветку
3. **Деплой**: Развернуть на тестовом окружении

### Краткосрочные (1-2 недели)
1. **BK-06**: Принять решение по Intent Mapper и реализовать
2. **Документация**: Обновить Swagger UI с новыми эндпоинтами
3. **Мониторинг**: Добавить метрики для новых API

### Долгосрочные
1. **Оптимизация**: Рассмотреть материализованные представления для словарей
2. **Кэширование**: Расширить кэширование для часто используемых запросов
3. **Аналитика**: Собирать статистику использования новых эндпоинтов

## Риски и ограничения

### Технические риски
1. **PostGIS производительность**: Accessor делает отдельный SQL-запрос для каждой координаты
2. **Кэширование словарей**: При изменении справочников нужен инвалидация кэша
3. **Миграция данных**: Для тестов нужны реальные данные с координатами

### Бизнес-риски
1. **Сроки**: Реализация заняла больше времени, чем планировалось (9ч vs 14-19ч)
2. **Качество**: Нужно тщательное тестирование перед продакшеном
3. **Поддержка**: Новые эндпоинты требуют документации для фронтенд-разработчиков

## Заключение

Реализованы все критические задачи беклога, необходимые для работы фронтенда:
- ✅ Геолокация на карте (координаты)
- ✅ Контактная информация в списке (телефон)
- ✅ Динамические фильтры (справочники)
- ✅ Контентная платформа (статьи)
- ✅ Точная фильтрация мероприятий (категории)

Задача BK-06 (Intent Mapper) требует архитектурного решения, для которого подготовлен ADR с рекомендацией простого JSON-подхода для MVP.

**Готово к код-ревью и интеграции с фронтендом.**