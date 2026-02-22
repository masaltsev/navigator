<?php

namespace Database\Seeders;

use App\Models\SpecialistProfile;
use Illuminate\Database\Console\Seeds\WithoutModelEvents;
use Illuminate\Database\Seeder;

/**
 * Seed specialist_profiles from dictionaries_refactoring.md Table B.
 */
class SpecialistProfileSeeder extends Seeder
{
    use WithoutModelEvents;

    /**
     * @return array<int, array{code: string, name: string}>
     */
    protected function rows(): array
    {
        return [
            ['code' => '96', 'name' => 'Волонтер'],
            ['code' => '120', 'name' => 'Офтальмолог'],
            ['code' => '122', 'name' => 'Сурдолог'],
            ['code' => '123', 'name' => 'ЛОР (Оториноларинголог)'],
            ['code' => '125', 'name' => 'Уролог'],
            ['code' => '126', 'name' => 'Диетолог / Нутрициолог'],
            ['code' => '127', 'name' => 'Мануальный терапевт'],
            ['code' => '128', 'name' => 'Эрготерапевт'],
            ['code' => '129', 'name' => 'Физиотерапевт'],
            ['code' => '130', 'name' => 'Реабилитолог'],
            ['code' => '132', 'name' => 'Ревматолог'],
            ['code' => '134', 'name' => 'Травматолог-ортопед'],
            ['code' => '137', 'name' => 'Эндокринолог'],
            ['code' => '141', 'name' => 'Психиатр / Геронтопсихиатр'],
            ['code' => '142', 'name' => 'Невролог'],
            ['code' => '143', 'name' => 'Гериатр'],
        ];
    }

    public function run(): void
    {
        foreach ($this->rows() as $row) {
            SpecialistProfile::updateOrCreate(
                ['code' => $row['code']],
                ['name' => $row['name'], 'is_active' => true]
            );
        }
    }
}
