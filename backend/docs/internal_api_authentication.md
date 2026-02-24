# Internal API — Static Bearer Token Authentication

> **Дата:** 2026-02-24  
> **Commit:** 52d478c (uncommitted)  
> **Область:** Backend — Internal API (`/api/internal/*`)  
> **Источник истины:** [docs/Navigator_Core_Model_and_API.md](../../docs/Navigator_Core_Model_and_API.md)

---

## Назначение

Internal API — закрытый интерфейс для приёма данных от AI-пайплайна (Harvester).
Эндпоинты не предназначены для внешних пользователей и не содержат персональных данных.

Авторизация реализована по схеме **Static Bearer Token** — единый общий секрет
между Harvester и Core API, передаваемый в заголовке `Authorization`.

---

## Архитектура

```
Harvester (Python)                         Core API (Laravel)
┌──────────────────┐                      ┌─────────────────────────┐
│ core_client/api.py│──── HTTP POST ────▶ │ AuthenticateInternalApi │
│                  │   Authorization:     │    (middleware)          │
│ CORE_API_TOKEN   │   Bearer <token>     │         │               │
│ = Bearer <token> │                      │         ▼               │
└──────────────────┘                      │  config('internal.     │
                                          │          api_token')    │
                                          │         │               │
                                          │    hash_equals()        │
                                          │         │               │
                                          │         ▼               │
                                          │  ImportController       │
                                          └─────────────────────────┘
```

### Компоненты

| Файл | Роль |
|------|------|
| `config/internal.php` | Конфигурация: читает `INTERNAL_API_TOKEN` из `.env` |
| `app/Http/Middleware/AuthenticateInternalApi.php` | Middleware: проверка Bearer-токена |
| `bootstrap/app.php` | Регистрация alias `auth.internal` |
| `routes/api.php` | Применение middleware к группе `internal/*` |

---

## Защищённые эндпоинты

| Метод | URL | Описание |
|-------|-----|----------|
| POST | `/api/internal/import/organizer` | Импорт организации |
| POST | `/api/internal/import/event` | Импорт события |
| POST | `/api/internal/import/batch` | Пакетный импорт |

Публичные эндпоинты (`/api/v1/*`) не затронуты и работают без авторизации.

---

## Логика middleware

1. Проверяет наличие `INTERNAL_API_TOKEN` в конфиге → `500` если не настроен.
2. Извлекает Bearer-токен из заголовка `Authorization` → `401` если отсутствует.
3. Сравнивает токены через `hash_equals()` (timing-safe) → `403` если не совпадает.
4. При успехе — пропускает запрос к контроллеру.

### Коды ответов при ошибке

| Код | Ситуация | Тело ответа |
|-----|----------|-------------|
| 401 | Нет заголовка `Authorization` | `{"message": "Unauthorized. Bearer token required."}` |
| 403 | Токен не совпадает | `{"message": "Forbidden. Invalid API token."}` |
| 500 | `INTERNAL_API_TOKEN` не задан в `.env` сервера | `{"message": "Internal API authentication is not configured."}` |

---

## Настройка

### Backend (`.env`)

```
INTERNAL_API_TOKEN=<64-char hex token>
```

Токен генерируется один раз:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

### Harvester (`.env`)

```
CORE_API_URL=http://backend.test
CORE_API_TOKEN=Bearer <тот же 64-char hex token>
```

Harvester-клиент (`core_client/api.py`) отправляет значение `CORE_API_TOKEN` as-is
в заголовке `Authorization`. Поэтому в Harvester `.env` указывается полный формат
`Bearer <token>`, а в Backend `.env` — только сам токен (middleware парсит через
`$request->bearerToken()`).

---

## Оценка уровня защиты

### Для чего подходит Static Bearer Token

- **Machine-to-machine API** без сессий и пользователей
- **Внутренние сервисы** в доверенной сети (localhost / VPN / private network)
- **Системы без персональных данных** — данные организаций (название, ИНН, адрес) являются публичными

### Что обеспечивает

| Свойство | Обеспечено? | Как |
|----------|-------------|-----|
| Аутентификация вызывающего | Да | Общий секрет 256 bit |
| Защита от перебора | Да | `hash_equals` (timing-safe), длина токена 64 hex = 2^256 комбинаций |
| Защита в транспорте | Частично | HTTPS на продакшене; на localhost HTTP допустим |
| Ротация токенов | Ручная | Замена в `.env` обоих сервисов + перезапуск |
| Гранулярность прав | Нет | Один токен = полный доступ ко всем internal эндпоинтам |
| Аудит-лог | Нет (можно добавить) | Логирование запросов в middleware при необходимости |

### Рекомендации при масштабировании

Если в будущем появятся требования, которые Static Bearer Token не покрывает,
рекомендуется перейти на **Laravel Sanctum** (API tokens с abilities):

| Триггер | Решение |
|---------|---------|
| Несколько внешних клиентов | Sanctum: отдельный токен на клиента |
| Гранулярные права (read-only / write) | Sanctum abilities: `import:write`, `sources:read` |
| Передача ПДн через API | TLS обязателен + Sanctum + rate limiting + audit log |
| Мульти-тенантность | Sanctum + политики (policies) |

На текущем этапе (внутренний API, один клиент, публичные данные) Static Bearer Token
полностью достаточен.

---

## Связанные документы

- [docs/Harvester_v1_Development_Plan.md](../../docs/Harvester_v1_Development_Plan.md) — бэклог, задача B6
- [ai-pipeline/harvester/core_client/api.py](../../ai-pipeline/harvester/core_client/api.py) — HTTP-клиент Harvester
