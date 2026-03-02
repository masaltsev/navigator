# Настройка Swagger / OpenAPI для Navigator Core API

**Дата:** 2026-02-28  
**Область:** документация API, OpenAPI 3.0, Swagger UI  
**Источник истины:** [docs/Navigator_Core_Model_and_API.md](../../../docs/Navigator_Core_Model_and_API.md), [backend/docs/reports/2026-02-27__api-tests-description.md](./2026-02-27__api-tests-description.md)

---

## 1. Что сделано

- **OpenAPI 3.0 спецификация** в YAML: `backend/storage/app/openapi.yaml`
  - Описаны все эндпоинты публичного контура (v1: organizations, events) и внутреннего (internal: import, sources).
  - Компоненты: схемы запросов/ответов (OrganizationListItem, OrganizationDetail, EventInstanceItem, ImportOrganizerRequest, ImportEventRequest, SourceItem и др.).
  - Security: Bearer token для внутреннего API.
  - Теги и описания на русском, ссылки на архитектурный документ и стек.

- **Маршруты документации:**
  - `GET /api/documentation` — страница Swagger UI (загружает спецификацию по URL).
  - `GET /api/documentation/spec` — отдача OpenAPI-спеки в формате YAML (`Content-Type: application/x-yaml`).

- **Контроллер:** `App\Http\Controllers\Api\DocumentationController` — отдача спеки и рендер представления.

- **Представление:** `resources/views/api/documentation.blade.php` — Swagger UI 5 (CDN: unpkg), загрузка спеки с `/api/documentation/spec`.

- Установлен пакет **darkaonline/l5-swagger** (для возможного использования аннотаций/генерации в будущем); основная точка входа — собственная реализация по OpenAPI 3 YAML.

---

## 2. Как открыть документацию

- Локально (например, Laravel Herd): **https://&lt;project&gt;.test/api/documentation**
- Или при `php artisan serve`: **http://127.0.0.1:8000/api/documentation**

Страница загружает спецификацию с того же хоста (`/api/documentation/spec`), поэтому CORS не требуется.

---

## 3. Проверка «Try it out» для internal

Для вызовов эндпоинтов с префиксом `/api/internal/*` в Swagger UI нужно задать Bearer-токен:

1. Нажать **Authorize**.
2. Ввести значение токена внутреннего API (например, из `config('internal.api_token')` или `.env`).
3. После этого запросы к internal-эндпоинтам будут отправляться с заголовком `Authorization: Bearer &lt;token&gt;`.

---

## 4. Связанные файлы

| Файл | Назначение |
|------|------------|
| `storage/app/openapi.yaml` | Исходная спецификация OpenAPI 3.0 (YAML). |
| `app/Http/Controllers/Api/DocumentationController.php` | Отдача спеки и страницы документации. |
| `resources/views/api/documentation.blade.php` | Страница Swagger UI. |
| `routes/api.php` | Маршруты `documentation` и `documentation/spec`. |

---

## 5. Дальнейшие шаги (по желанию)

- Добавить генерацию JSON-версии спеки (например, второй маршрут `/api/documentation/spec.json`) для клиентов, работающих только с JSON.
- При необходимости — экспорт статического `openapi.json` в репозиторий или артефакты сборки.
- Синхронизировать описание полей в `openapi.yaml` с реальными API Resources (OrganizationResource, EventResource) при изменении контрактов.
