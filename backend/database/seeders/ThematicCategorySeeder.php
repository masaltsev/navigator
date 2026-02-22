<?php

namespace Database\Seeders;

use App\Models\ThematicCategory;
use Illuminate\Database\Console\Seeds\WithoutModelEvents;
use Illuminate\Database\Seeder;

/**
 * Seed thematic_categories (life situations) from dictionaries_refactoring.md Table A.
 * Two passes: roots (parent_code null), then children by parent_code.
 * Codes 19 and 13 omitted (mapped 19→7, 13→8 at WP import). 21, 22, 23 are in services only.
 */
class ThematicCategorySeeder extends Seeder
{
    use WithoutModelEvents;

    /**
     * @return array<int, array{code: string, name: string, parent_code: ?string}>
     */
    protected function rows(): array
    {
        return [
            ['code' => '3', 'name' => 'Здоровье и уход', 'parent_code' => null],
            ['code' => '4', 'name' => 'Быт и социальная поддержка', 'parent_code' => null],
            ['code' => '5', 'name' => 'Активная жизнь', 'parent_code' => null],
            ['code' => '7', 'name' => 'Снижение памяти и деменция', 'parent_code' => '3'],
            ['code' => '8', 'name' => 'Остеопороз и риски падений', 'parent_code' => '3'],
            ['code' => '9', 'name' => 'Урологические состояния', 'parent_code' => '3'],
            ['code' => '10', 'name' => 'Управление болью', 'parent_code' => '3'],
            ['code' => '11', 'name' => 'Питание и диета', 'parent_code' => '3'],
            ['code' => '12', 'name' => 'Зрение и здоровье глаз', 'parent_code' => '3'],
            ['code' => '14', 'name' => 'Восстановление после инсульта', 'parent_code' => '3'],
            ['code' => '15', 'name' => 'Травмы и реабилитация', 'parent_code' => '3'],
            ['code' => '16', 'name' => 'Слух и слухопротезирование', 'parent_code' => '3'],
            ['code' => '17', 'name' => 'Паллиативная помощь', 'parent_code' => '3'],
            ['code' => '18', 'name' => 'Нуждаемость в постороннем уходе', 'parent_code' => '4'],
            ['code' => '20', 'name' => 'Одинокое проживание', 'parent_code' => '4'],
            ['code' => '24', 'name' => 'Поддержание здоровья и ЗОЖ', 'parent_code' => '5'],
            ['code' => '25', 'name' => 'Общение и социализация', 'parent_code' => '5'],
            ['code' => '26', 'name' => 'Карьера и образование', 'parent_code' => '5'],
            ['code' => '27', 'name' => 'Уход за собой и стиль', 'parent_code' => '5'],
            ['code' => '28', 'name' => 'Творчество и увлечения', 'parent_code' => '5'],
            ['code' => '29', 'name' => 'Путешествия и туризм', 'parent_code' => '5'],
        ];
    }

    public function run(): void
    {
        $rows = $this->rows();
        $roots = array_filter($rows, fn ($r) => $r['parent_code'] === null);
        $children = array_filter($rows, fn ($r) => $r['parent_code'] !== null);

        foreach ($roots as $row) {
            ThematicCategory::updateOrCreate(
                ['code' => $row['code']],
                ['name' => $row['name'], 'is_active' => true, 'parent_id' => null]
            );
        }

        foreach ($children as $row) {
            $parent = ThematicCategory::where('code', $row['parent_code'])->first();
            ThematicCategory::updateOrCreate(
                ['code' => $row['code']],
                [
                    'name' => $row['name'],
                    'is_active' => true,
                    'parent_id' => $parent?->id,
                ]
            );
        }
    }
}
