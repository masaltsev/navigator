<?php

namespace Database\Seeders;

use App\Models\OrganizationType;
use Illuminate\Database\Console\Seeds\WithoutModelEvents;
use Illuminate\Database\Seeder;

/**
 * Seed organization_types from dictionaries_refactoring.md Table B (new names only).
 */
class OrganizationTypeSeeder extends Seeder
{
    use WithoutModelEvents;

    /**
     * @return array<int, array{code: string, name: string}>
     */
    protected function rows(): array
    {
        return [
            ['code' => '65', 'name' => 'ПНИ / Интернат'],
            ['code' => '69', 'name' => 'Культурное учреждение'],
            ['code' => '71', 'name' => 'Модельное агентство'],
            ['code' => '73', 'name' => 'Косметологический центр'],
            ['code' => '79', 'name' => 'Центр занятости населения'],
            ['code' => '82', 'name' => 'Досуговый центр'],
            ['code' => '92', 'name' => 'Клуб/Центр здоровья'],
            ['code' => '99', 'name' => 'Кризисный центр'],
            ['code' => '103', 'name' => 'Реабилитационный центр'],
            ['code' => '112', 'name' => 'Специализированный стационар (деменция)'],
            ['code' => '118', 'name' => 'Хоспис / Паллиативное отделение'],
            ['code' => '121', 'name' => 'Сурдологический центр'],
            ['code' => '124', 'name' => 'Урологическое отделение'],
            ['code' => '138', 'name' => 'Медицинская школа для пациентов'],
            ['code' => '139', 'name' => 'Клиника памяти'],
            ['code' => '140', 'name' => 'Гериатрическое отделение'],
        ];
    }

    public function run(): void
    {
        foreach ($this->rows() as $row) {
            OrganizationType::updateOrCreate(
                ['code' => $row['code']],
                ['name' => $row['name'], 'is_active' => true]
            );
        }
    }
}
