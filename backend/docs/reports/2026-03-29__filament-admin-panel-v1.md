# Filament admin panel v1 (operational UI)

- **Date**: 2026-03-29
- **Git commit**: `b633368` (на момент составления отчёта; уточните `git rev-parse --short HEAD` после мержа)
- **Scope**: `backend/` — Filament v3, `app/Filament/`, `app/Console/Commands/CreateAdminUser.php`, миграция `users.is_admin`, модели `Organization`, `OrganizationType`, `Venue`, `User`
- **Пользовательская документация**: [admin_panel.md](../admin_panel.md)

## Цель

Первая версия веб-админки на **Filament v3** для контент- и операционных задач: CRUD сущностей домена, связи со справочниками, фильтры/поиск, сценарии review после LLM-обхода и мониторинг обходов источников — без полноценной RBAC (только флаг `is_admin`).

## Что сделано

### Инфраструктура и доступ

- Зависимость `filament/filament` (^3), панель по умолчанию: путь **`/admin`**, провайдер [`app/Providers/Filament/AdminPanelProvider.php`](../../app/Providers/Filament/AdminPanelProvider.php), бренд **Navigator**.
- Миграция [`database/migrations/2026_03_29_104815_add_is_admin_to_users_table.php`](../../database/migrations/2026_03_29_104815_add_is_admin_to_users_table.php): колонка `users.is_admin` (boolean, default false).
- Модель [`User`](../../app/Models/User.php): контракт `FilamentUser`, `canAccessPanel()` → `is_admin`; в `fillable` добавлены `is_admin`, `email_verified_at`.
- Команда **`php artisan admin:create {email} {password}`** — создание или обновление пользователя с полным доступом к панели ([`CreateAdminUser`](../../app/Console/Commands/CreateAdminUser.php)).
- Тесты: [`tests/Feature/Console/CreateAdminUserCommandTest.php`](../../tests/Feature/Console/CreateAdminUserCommandTest.php).

### Ресурсы Filament (навигация по группам)

| Группа | Ресурсы |
|--------|---------|
| **Entities** | Organization, Event, Organizer, Venue, Individual, InitiativeGroup |
| **Content** | Article (Markdown) |
| **Dictionaries** | ThematicCategory, Service, OrganizationType, OwnershipType, CoverageLevel, SpecialistProfile, EventCategory, TargetAudience |
| **Harvester** | Source, ParseProfile, SuggestedTaxonomyItem, EventInstance |
| **System** | User |

### Связи и особенности домена

- **Organization**: форма с секцией `organizer` (morphOne), чеклисты/мультиселекты к справочникам, relation managers: venues (pivot `is_headquarters`), events, articles, suggested taxonomy; подсказки по дубликатам ИНН/ОГРН; после `create` при отсутствии — создаётся пустой organizer.
- **OrganizationType**: исправлена связь `organizations()` на `BelongsToMany` через `organization_organization_types` (соответствие схеме БД).
- **Organization**: добавлено `suggestedTaxonomyItems()` (`HasMany`).
- **Event**: instances, venues (attach), табы списка, быстрые approve/reject.
- **Organizer**: полиморфная привязка к Organization / InitiativeGroup / Individual; sources, events, users; глобальный поиск отключён (`canGloballySearch()`).
- **Venue**: lat/lng в форме → [`Venue::updateCoordinatesFromLatLng()`](../../app/Models/Venue.php) (PostGIS `ST_MakePoint`); страницы Create/Edit снимают координаты из формы.
- **Source**: фильтры по `kind`, `last_status`, диапазону `last_crawled_at`; табы Active/Inactive; виджет «недавно обходили».
- **SuggestedTaxonomyItem**: bulk approve/reject.
- Вспомогательный класс бейджей статусов: [`app/Filament/Support/StatusColors.php`](../../app/Filament/Support/StatusColors.php).

### Дашборд

- [`NavigatorStatsOverview`](../../app/Filament/Widgets/NavigatorStatsOverview.php) — счётчики organizations, events, sources, articles, users.
- [`LatestInReviewOrganizationsWidget`](../../app/Filament/Widgets/LatestInReviewOrganizationsWidget.php) — последние организации со статусом `in_review`.
- [`LatestCrawledSourcesWidget`](../../app/Filament/Widgets/LatestCrawledSourcesWidget.php) — источники с недавним `last_crawled_at`.

### Списки с табами (workflow)

- Organizations: All / In review / Approved.
- Events: All / In review / Approved.
- Sources: All / Active / Inactive.

## Ограничения v1 (ожидаемо)

- Ролевая модель не реализована: любой пользователь с `is_admin = true` имеет полный доступ к панели.
- «Всё на одном экране» для организации: организатор и справочники — в одной форме; **источник** и **площадка** — через relation managers / отдельные ресурсы (не единый мастер-wizard).
- Глобальный поиск по Organizer по имени связанной сущности не включён (отключён сознательно).
- Сравнение «что изменилось после обхода» не автоматизировано: ориентир — `updated_at` у организаций/событий и фильтры по дате обхода у источников.

## Проверки

- `php artisan migrate`
- `php artisan test` (в т.ч. `CreateAdminUserCommandTest`)

## Ссылки

- План внедрения (ТЗ): `.cursor/plans/filament_admin_panel_launch_b920a156.plan.md` (в репозитории Cursor; не часть `backend/docs`).
