# Удаление тестовых организаций "Lookup Test Org"

Тестовые организации с `title = 'Lookup Test Org'` и `source_reference LIKE 'lookup_test_%'` не должны были попасть из WordPress; их нужно удалить на dev и на проде.

## Вариант 1: через Tinker (рекомендуется)

На сервере в каталоге `backend`:

```bash
php artisan tinker
```

В Tinker вставить и выполнить:

```php
$ids = \App\Models\Organization::where('title', 'Lookup Test Org')->where('source_reference', 'like', 'lookup_test_%')->pluck('id');
$count = $ids->count();
if ($count === 0) { echo "No Lookup Test Org found.\n"; exit; }
\Illuminate\Support\Facades\DB::transaction(function () use ($ids) {
    foreach ($ids as $orgId) {
        $org = \App\Models\Organization::withTrashed()->find($orgId);
        if (!$org) continue;
        $organizer = \App\Models\Organizer::withTrashed()->where('organizable_type', 'Organization')->where('organizable_id', $orgId)->first();
        if ($organizer) $organizer->forceDelete();
        $org->forceDelete();
    }
});
echo "Deleted {$count} Lookup Test Org(s).\n";
```

## Вариант 2: одна строка для Tinker --execute

Если Tinker не ругается на запись в history (или запуск без интерактива):

```bash
cd backend && php artisan tinker --execute="
\$ids = \App\Models\Organization::where('title', 'Lookup Test Org')->where('source_reference', 'like', 'lookup_test_%')->pluck('id');
\$n = \$ids->count();
if (\$n === 0) { echo 'No Lookup Test Org.'; return; }
\Illuminate\Support\Facades\DB::transaction(function () use (\$ids) {
    foreach (\$ids as \$id) {
        \$org = \App\Models\Organization::withTrashed()->find(\$id);
        if (!\$org) continue;
        \App\Models\Organizer::withTrashed()->where('organizable_type', 'Organization')->where('organizable_id', \$id)->first()?->forceDelete();
        \$org->forceDelete();
    }
});
echo \"Deleted {\$n} Lookup Test Org(s).\n\";
"
```

## Вариант 3: сырой SQL (если без Laravel / только БД)

Сначала получить id организаций и организаторов:

```sql
SELECT o.id AS org_id, p.id AS organizer_id
FROM organizations o
LEFT JOIN organizers p ON p.organizable_type = 'Organization' AND p.organizable_id = o.id
WHERE o.title = 'Lookup Test Org' AND o.source_reference LIKE 'lookup_test_%';
```

Затем удалить (порядок важен: события привязаны к organizer_id CASCADE, источники — SET NULL):

1. Удалить организаторов (события удалятся по CASCADE):

```sql
DELETE FROM organizers
WHERE organizable_type = 'Organization'
  AND organizable_id IN (
    SELECT id FROM organizations
    WHERE title = 'Lookup Test Org' AND source_reference LIKE 'lookup_test_%'
  );
```

2. Окончательно удалить организации (pivot-таблицы по organization_id — CASCADE):

```sql
DELETE FROM organizations
WHERE title = 'Lookup Test Org' AND source_reference LIKE 'lookup_test_%';
```

Если в таблице `organizations` используется soft delete (`deleted_at`), то вместо `DELETE` для организаций можно обновить:  
`UPDATE organizations SET deleted_at = now() WHERE title = 'Lookup Test Org' AND source_reference LIKE 'lookup_test_%';`  
но тогда шаг 1 (DELETE organizers) всё равно нужен, и позже «мусор» из `organizers` лучше удалить отдельно.
