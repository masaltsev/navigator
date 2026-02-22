# Инструкция по очистке кода после завершения миграции из WordPress

## Контекст

После успешного завершения миграции данных из WordPress/HivePress в Navigator Core (команда `php artisan navigator:migrate-from-wp-base`) код миграции больше не нужен, так как это разовый процесс. Данная инструкция описывает шаги по удалению временных файлов и конфигураций.

**⚠️ ВАЖНО:** Выполняйте очистку только после:
1. Успешного завершения миграции всех данных
2. Проверки корректности перенесенных данных в Core БД
3. Подтверждения, что повторная миграция не потребуется

---

## Шаги очистки

### 1. Удаление сервисов миграции

Удалите следующие файлы из директории `app/Services/WpMigration/`:

```bash
rm -rf app/Services/WpMigration/
```

**Удаляемые файлы:**
- `app/Services/WpMigration/WpListingRepository.php`
- `app/Services/WpMigration/WpTaxonomyMapper.php`
- `app/Services/WpMigration/WpToCoreMigrator.php`

**Проверка:** Убедитесь, что директория `app/Services/WpMigration/` полностью удалена или пуста.

---

### 2. Удаление консольной команды

Удалите файл команды миграции:

```bash
rm app/Console/Commands/MigrateFromWpBaseCommand.php
```

**Проверка:** Выполните `php artisan list | grep navigator` — команда `navigator:migrate-from-wp-base` не должна отображаться в списке.

---

### 3. Удаление подключения к WordPress БД из конфигурации

Откройте файл `config/database.php` и удалите блок подключения `mysql_wp`:

**Найти и удалить:**
```php
/*
|--------------------------------------------------------------------------
| WordPress Legacy Database Connection
|--------------------------------------------------------------------------
|
| Connection to the legacy WordPress/HivePress MySQL database for
| data migration purposes. Used by the navigator:migrate-from-wp-base
| command.
|
| Add these variables to your .env file:
| DB_WP_HOST=127.0.0.1
| DB_WP_PORT=3306
| DB_WP_DATABASE=navigator_wp
| DB_WP_USERNAME=navigator_wp_user
| DB_WP_PASSWORD=navigator_wp_password
|
*/

'mysql_wp' => [
    'driver' => 'mysql',
    'host' => env('DB_WP_HOST', '127.0.0.1'),
    'port' => env('DB_WP_PORT', '3306'),
    'database' => env('DB_WP_DATABASE', 'navigator_wp'),
    'username' => env('DB_WP_USERNAME', 'navigator_wp_user'),
    'password' => env('DB_WP_PASSWORD', 'navigator_wp_password'),
    'charset' => 'utf8mb4',
    'collation' => 'utf8mb4_unicode_ci',
    'prefix' => 'wp_',
    'prefix_indexes' => true,
    'strict' => true,
    'engine' => null,
],
```

**Проверка:** Убедитесь, что в `config/database.php` нет упоминаний `mysql_wp`.

---

### 4. Удаление переменных окружения (опционально)

Если вы добавляли переменные `DB_WP_*` в файл `.env`, их можно удалить:

```bash
# Удалите следующие строки из .env (если они были добавлены):
DB_WP_HOST=127.0.0.1
DB_WP_PORT=3306
DB_WP_DATABASE=navigator_wp
DB_WP_USERNAME=navigator_wp_user
DB_WP_PASSWORD=navigator_wp_password
```

**Примечание:** Если переменные не были добавлены в `.env` (использовались значения по умолчанию из `config/database.php`), этот шаг можно пропустить.

---

### 5. Проверка зависимостей

Проверьте, что удаленные классы не используются в других частях кода:

```bash
# Поиск упоминаний удаленных классов
grep -r "WpListingRepository" app/
grep -r "WpTaxonomyMapper" app/
grep -r "WpToCoreMigrator" app/
grep -r "MigrateFromWpBaseCommand" app/
grep -r "mysql_wp" app/ config/
```

**Ожидаемый результат:** Команды не должны находить упоминаний (или находить только в документации).

---

### 6. Очистка кэша Laravel

После удаления файлов очистите кэш Laravel:

```bash
php artisan config:clear
php artisan cache:clear
php artisan route:clear
```

---

## Документация (рекомендация)

### Что оставить

Рекомендуется **оставить** следующие файлы документации для исторической справки:

- `docs/wp_to_core_migration.md` (корень репозитория) — описание процесса миграции и маппинга данных
- `wp_migration_design.md` (здесь, в backend/docs) — архитектура решения (может быть полезно для понимания структуры данных)

### Что можно удалить (опционально)

Если документация по миграции больше не нужна:

```bash
# Из корня репозитория. Удалить только если уверены, что документация не потребуется
rm backend/docs/wp_migration_design.md
```

**Примечание:** `docs/wp_to_core_migration.md` (в корне) лучше оставить — важная информация о маппинге данных для анализа структуры БД.

---

## Финальная проверка

После выполнения всех шагов проверьте:

1. ✅ Команда `php artisan navigator:migrate-from-wp-base` отсутствует в списке команд
2. ✅ В `config/database.php` нет подключения `mysql_wp`
3. ✅ Директория `app/Services/WpMigration/` удалена
4. ✅ Файл `app/Console/Commands/MigrateFromWpBaseCommand.php` удален
5. ✅ Код компилируется без ошибок (`php artisan config:cache`)
6. ✅ Тесты проходят (если есть)

---

## Автоматизация очистки

Если хотите автоматизировать процесс, можно создать временную команду для очистки:

```bash
php artisan make:command CleanupWpMigrationCommand
```

Но проще выполнить шаги вручную, чтобы контролировать процесс.

---

## Откат (если потребуется повторная миграция)

Если после очистки потребуется повторная миграция:

1. Восстановите файлы из git истории:
   ```bash
   git checkout <commit-before-cleanup> -- app/Services/WpMigration/
   git checkout <commit-before-cleanup> -- app/Console/Commands/MigrateFromWpBaseCommand.php
   git checkout <commit-before-cleanup> -- config/database.php
   ```

2. Или создайте новую ветку с кодом миграции для архивации перед очисткой.

---

**Дата создания инструкции:** 2026-02-16  
**Статус:** Готово к использованию после завершения миграции
