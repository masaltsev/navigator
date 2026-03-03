# Анализ иерархии таксономий WordPress → Core

**Дата:** 16 февраля 2026  
**Проблема:** Иерархическая структура таксономий WordPress не перенесена в Core справочники

---

## Структура в WordPress

### Категории проблем (hp_listing_category)

**Родительские категории:**

1. **Активное долголетие** (term_id: 5)
   - Карьера и образование (term_id: 26)
   - Мода и красота (term_id: 27)
   - **Социальная вовлеченность** (term_id: 25) ← дочерняя категория
   - Туризм (term_id: 29)
   - Укрепление здоровья (term_id: 24)
   - Хобби и досуг (term_id: 28)

2. **Медицинская помощь** (term_id: 3)
   - Недержание мочи (term_id: 9)
   - Необходимость реабилитации (term_id: 15)
   - Остеопороз, падения и переломы (term_id: 8)
   - Паллиативная помощь (term_id: 17)
   - Последствия инсульта (term_id: 14)
   - Проблемы с памятью и когнитивные нарушения (term_id: 7)
   - Проблемы с питанием (term_id: 11)
   - Проблемы со зрением (term_id: 12)
   - Проблемы со слухом (term_id: 16)
   - Хроническая боль (term_id: 10)
   - Частые падения (term_id: 13)

3. **Социальные услуги** (term_id: 4) ← родительская категория
   - Когнитивные нарушения (term_id: 19)
   - Одинокое проживание (term_id: 20)
   - Потеря автономности (term_id: 18)
   - Социальная Реабилитация (term_id: 21)
   - Социальное такси (term_id: 23)
   - Срочная помощь (term_id: 22)

---

## Структура в Core

### Таблица `problem_categories`

**Колонки:**
- `id` (bigint) - автоинкремент
- `name` (varchar)
- `code` (varchar) - соответствует WordPress term_id
- `is_active` (boolean)
- `created_at`, `updated_at`, `deleted_at`

**Проблема:** ❌ **Нет колонки `parent_id`**

Все категории хранятся как плоский список без иерархии.

---

## Сравнение

### WordPress
- ✅ Иерархическая структура через поле `parent` в `term_taxonomy`
- ✅ "Социальные услуги" (ID: 4) — родитель
- ✅ "Социальная вовлеченность" (ID: 25) — дочерняя категория "Активного долголетия" (ID: 5)

### Core
- ❌ Плоская структура без иерархии
- ❌ Нет поля `parent_id` в таблице `problem_categories`
- ❌ `ProblemCategorySeeder` не обрабатывает поле `parent` из WordPress

---

## Проблемы

1. **Отсутствие колонки `parent_id`** в таблице `problem_categories`
2. **Сидер не обрабатывает иерархию** — `ProblemCategorySeeder` не извлекает поле `parent` из WordPress
3. **Потеря семантики** — невозможно определить родительско-дочерние связи между категориями

---

## Решение

### 1. Добавить колонку `parent_id` в таблицу `problem_categories`

Создать миграцию:
```php
Schema::table('problem_categories', function (Blueprint $table) {
    $table->foreignId('parent_id')
        ->nullable()
        ->after('code')
        ->constrained('problem_categories')
        ->nullOnDelete();
});
```

### 2. Обновить `ProblemCategorySeeder`

Добавить обработку иерархии аналогично `ServiceSeeder`:

```php
// Первый проход: создать все категории без parent_id
foreach ($categories as $category) {
    ProblemCategory::updateOrCreate(
        ['code' => (string) $category->term_id],
        [
            'name' => trim($category->name),
            'is_active' => true,
            'parent_id' => null, // Будет установлено во втором проходе
        ]
    );
}

// Второй проход: установить parent_id
// WordPress parent хранится как term_taxonomy_id, нужно найти соответствующий term_id
$parentMap = [];
foreach ($categories as $category) {
    if ($category->parent > 0) {
        // Найти parent term_id по term_taxonomy_id
        $parentTerm = $wpConnection->selectOne("
            SELECT term_id 
            FROM {$termTaxonomyTable} 
            WHERE term_taxonomy_id = ?
        ", [$category->parent]);
        
        if ($parentTerm) {
            $parentMap[$category->term_id] = $parentTerm->term_id;
        }
    }
}

// Обновить parent_id
foreach ($parentMap as $termId => $parentTermId) {
    $category = ProblemCategory::where('code', (string) $termId)->first();
    $parentCategory = ProblemCategory::where('code', (string) $parentTermId)->first();
    
    if ($category && $parentCategory) {
        $category->update(['parent_id' => $parentCategory->id]);
    }
}
```

### 3. Обновить модель `ProblemCategory`

Добавить отношения:
```php
public function parent(): BelongsTo
{
    return $this->belongsTo(ProblemCategory::class, 'parent_id');
}

public function children(): HasMany
{
    return $this->hasMany(ProblemCategory::class, 'parent_id');
}
```

---

## Проверка для Services

В таблице `services` уже есть колонка `parent_id` и `ServiceSeeder` обрабатывает иерархию корректно. Это хороший пример для реализации в `problem_categories`.

---

## Рекомендации

1. ✅ **Добавить миграцию** для колонки `parent_id` в `problem_categories`
2. ✅ **Обновить `ProblemCategorySeeder`** для сохранения иерархии
3. ✅ **Обновить модель `ProblemCategory`** с отношениями parent/children
4. ✅ **Перезапустить сидер** для восстановления иерархии
5. ✅ **Проверить API** — возможно, нужно добавить поддержку фильтрации по родительским категориям

---

## Влияние на текущие данные

После добавления иерархии:
- Существующие связи организаций с категориями **не изменятся**
- Можно будет фильтровать организации по родительским категориям (например, найти все организации с категориями из группы "Социальные услуги")
- Улучшится навигация и группировка категорий в UI
