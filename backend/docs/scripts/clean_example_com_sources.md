# Очистка тестовых источников example.com

**Правило:** тесты, создающие организации и источники с тестовыми данными (например «Source Test Org», «Lookup by Source ID Org», URL на example.com), **не должны запускаться на продовой базе**. Такие тесты (Feature, в т.ч. `SourceTest`, `ImportTest`) пишут в БД; на проде для тестов должна использоваться отдельная БД или тесты не должны выполняться против продовой БД вообще.

---

Источники с `base_url` содержащим **example.com** (new-url, patch-before, existing, due-test, dup, list-test, org-site, source-lookup-test, show-test, registry-fpg и т.д.) созданы фикстурами тестов (Feature/SourceTest и др.). Они привязаны к организациям со статусом **approved** (например «Source Test Org», «Lookup by Source ID Org»), поэтому попадают в `harvest:dispatch-due` и уезжают на прод вместе с дампом БД.

Рекомендация: на **проде** (и при желании на dev) сначала деактивировать такие источники, затем при необходимости удалить тестовые организации.

---

## 1. Быстрый фикс: деактивировать источники example.com

После этого они перестают попадать в due (`scopeDue` требует `is_active = true`).

### SQL

```sql
UPDATE sources
SET is_active = false
WHERE base_url ILIKE '%example.com%'
  AND deleted_at IS NULL;
```

### Tinker

```php
$n = \App\Models\Source::where('base_url', 'like', '%example.com%')->update(['is_active' => false]);
echo "Deactivated {$n} source(s).\n";
```

### Без Tinker (одной командой, удобно на проде)

Из каталога `backend`:

```bash
php -r "
require 'vendor/autoload.php';
\$app = require_once 'bootstrap/app.php';
\$app->make('Illuminate\Contracts\Console\Kernel')->bootstrap();
\$n = \App\Models\Source::where('base_url', 'like', '%example.com%')->update(['is_active' => false]);
echo \"Deactivated {\$n} source(s).\n\";
"
```

Проверка после выполнения:

```bash
php artisan harvest:dispatch-due --dry-run
```

В списке не должно быть URL с example.com.

---

## 2. (Опционально) Удалить тестовые организации и их организаторов

Организации с названиями **«Source Test Org»** и **«Lookup by Source ID Org»** — чисто тестовые. Их удаление освобождает БД; у источников, привязанных к ним, после удаления организатора выставится `organizer_id = NULL` (FK ON DELETE SET NULL), и они не будут попадать в due.

Организация **«СилаДобра»** с двумя источниками example.com — не тестовая; для неё достаточно деактивации этих двух источников (шаг 1).

### Tinker

В Tinker при выводе большой коллекции (например `$ids`) может открыться пейджер **less** — нажмите **`q`**, чтобы выйти и продолжить. Вставляйте код **целиком** или по блокам (не разбивайте `if` и `else` по разным вводам — будет parse error). Вариант в одну «логическую» порцию:

```php
$titles = ['Source Test Org', 'Lookup by Source ID Org'];
$ids = \App\Models\Organization::whereIn('title', $titles)->pluck('id');
$count = $ids->count();
if ($count === 0) { echo "No test orgs found.\n"; }
else {
  \Illuminate\Support\Facades\DB::transaction(function () use ($ids) {
    foreach ($ids as $orgId) {
      $org = \App\Models\Organization::withTrashed()->find($orgId);
      if (!$org) continue;
      $organizer = \App\Models\Organizer::withTrashed()->where('organizable_type', 'Organization')->where('organizable_id', $orgId)->first();
      if ($organizer) $organizer->forceDelete();
      $org->forceDelete();
    }
  });
  echo "Deleted {$count} test organization(s).\n";
}
```

### Без Tinker (одной командой, рекомендуется на проде)

Так не будет пейджера и не нужно вставлять код по частям. Из каталога `backend`:

```bash
php -r "
require 'vendor/autoload.php';
\$app = require_once 'bootstrap/app.php';
\$app->make('Illuminate\Contracts\Console\Kernel')->bootstrap();
\$titles = ['Source Test Org', 'Lookup by Source ID Org'];
\$ids = \App\Models\Organization::whereIn('title', \$titles)->pluck('id');
\$count = \$ids->count();
if (\$count === 0) { echo \"No test orgs found.\n\"; exit(0); }
\Illuminate\Support\Facades\DB::transaction(function () use (\$ids) {
    foreach (\$ids as \$orgId) {
        \$org = \App\Models\Organization::withTrashed()->find(\$orgId);
        if (!\$org) continue;
        \$organizer = \App\Models\Organizer::withTrashed()->where('organizable_type', 'Organization')->where('organizable_id', \$orgId)->first();
        if (\$organizer) \$organizer->forceDelete();
        \$org->forceDelete();
    }
});
echo \"Deleted {\$count} test organization(s).\n\";
"
```

После этого источники с example.com, бывшие привязанными к этим организаторам, останутся в таблице с `organizer_id = NULL` и не будут участвовать в due. При желании их можно удалить или оставить (шаг 1 уже отключил их через `is_active = false`, если выполнялся первым).

---

## Сводка по локальной базе (на момент написания)

- Источников с `base_url` содержащим **example.com**: 120.
- Все привязаны к организациям со статусом **approved**.
- Названия организаций: в основном «Source Test Org», «Lookup by Source ID Org»; у двух источников (example.com, example.com/1) — «СилаДобра».

Чтобы на проде в `harvest:dispatch-due` не уходили тестовые URL, достаточно выполнить **шаг 1** (деактивация источников example.com).
