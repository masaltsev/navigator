<?php

namespace Database\Seeders;

use App\Models\OwnershipType;
use Illuminate\Database\Console\Seeds\WithoutModelEvents;
use Illuminate\Database\Seeder;

/**
 * Seed ownership types (form of ownership / ОПФ).
 *
 * Static data preserves code mapping for AI pipeline and external references.
 * Originally from WordPress taxonomy hp_listing_ownership (term_id → code).
 */
class OwnershipTypeSeeder extends Seeder
{
    use WithoutModelEvents;

    /**
     * @return array<int, array{code: string, name: string}>
     */
    protected function rows(): array
    {
        return [
            ['code' => '151', 'name' => 'Тест ОПФ'],
            ['code' => '152', 'name' => 'Государственное автономное учреждение субъекта Российской Федерации'],
            ['code' => '153', 'name' => 'Муниципальное бюджетное учреждение'],
            ['code' => '154', 'name' => 'Государственное бюджетное учреждение субъекта Российской Федерации'],
            ['code' => '155', 'name' => 'Профсоюзная организация'],
            ['code' => '156', 'name' => 'Учреждение'],
            ['code' => '157', 'name' => 'Учреждение, созданное субъектом Российской Федерации'],
            ['code' => '158', 'name' => 'Непубличное акционерное общество'],
            ['code' => '159', 'name' => 'Государственное казенное учреждение субъекта Российской Федерации'],
            ['code' => '160', 'name' => 'Филиал юридического лица'],
            ['code' => '161', 'name' => 'Фонд'],
            ['code' => '162', 'name' => 'Автономная некоммерческая организация'],
            ['code' => '163', 'name' => 'Общество с ограниченной ответственностью'],
            ['code' => '164', 'name' => 'Федеральное государственное бюджетное учреждение'],
            ['code' => '165', 'name' => 'Общественная организация'],
            ['code' => '166', 'name' => 'Муниципальное автономное учреждение'],
            ['code' => '167', 'name' => 'Муниципальное казенное учреждение'],
        ];
    }

    public function run(): void
    {
        foreach ($this->rows() as $row) {
            OwnershipType::updateOrCreate(
                ['code' => $row['code']],
                ['name' => $row['name'], 'is_active' => true]
            );
        }
    }
}
