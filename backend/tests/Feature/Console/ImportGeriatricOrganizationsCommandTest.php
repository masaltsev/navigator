<?php

use App\Models\Organization;
use App\Models\OrganizationType;
use App\Models\SpecialistProfile;
use Illuminate\Support\Str;
use PhpOffice\PhpSpreadsheet\Cell\Coordinate;
use PhpOffice\PhpSpreadsheet\Spreadsheet;
use PhpOffice\PhpSpreadsheet\Writer\Xlsx;
use Tests\Concerns\RefreshDatabaseWithSchema;

uses(RefreshDatabaseWithSchema::class);

function writeXlsx(array $rows): string
{
    $spreadsheet = new Spreadsheet;
    $sheet = $spreadsheet->getActiveSheet();

    $r = 1;
    foreach ($rows as $row) {
        $c = 1;
        foreach ($row as $cell) {
            $addr = Coordinate::stringFromColumnIndex($c).$r;
            $sheet->setCellValue($addr, $cell);
            $c++;
        }
        $r++;
    }

    $path = sys_get_temp_dir().'/gerontology-'.Str::uuid().'.xlsx';
    (new Xlsx($spreadsheet))->save($path);

    return $path;
}

test('gerontology:import dry-run matches existing org and plans attachments', function (): void {
    OrganizationType::query()->firstOrCreate(['code' => '140'], ['name' => 'Гериатрическое отделение']);
    SpecialistProfile::query()->firstOrCreate(['code' => '143'], ['name' => 'Гериатр']);

    $existing = Organization::factory()->approved()->create([
        'title' => 'КГБУЗ "Алтайский краевой госпиталь для ветеранов войн"',
    ]);

    $centersXlsx = writeXlsx([
        ['Субъект РФ', 'Название гериатрического центра', 'Наименование учреждения на базе которого был открыт гериатрический центр', 'Год открытия', 'Адрес учреждения на базе которого открыт гериатрический центр'],
        ['Алтайский край', 'Алтайский краевой гериатрический центр', $existing->title, '2019', '656045, Змеиногорский тракт, д.112, г. Барнаул, Алтайский край'],
    ]);

    $outDir = sys_get_temp_dir().'/gerontology-out-'.Str::uuid();

    $this->artisan('gerontology:import', [
        '--dry-run' => true,
        '--centers' => $centersXlsx,
        '--out-dir' => $outDir,
    ])->assertSuccessful();

    $json = file_get_contents($outDir.'/plan.json');
    expect($json)->not->toBeFalse();

    $plan = json_decode($json, true);
    expect($plan)->toBeArray()
        ->and($plan['items'])->toHaveCount(1)
        ->and($plan['items'][0]['match']['organization_id'])->toBe($existing->id)
        ->and($plan['items'][0]['actions'])->toContain(['type' => 'attach_organization_type', 'organization_type_code' => '140'])
        ->and($plan['items'][0]['actions'])->toContain(['type' => 'attach_specialist_profile', 'specialist_profile_code' => '143']);
});

test('gerontology:import dry-run plans creating org for cabinet', function (): void {
    OrganizationType::query()->firstOrCreate(['code' => '140'], ['name' => 'Гериатрическое отделение']);
    SpecialistProfile::query()->firstOrCreate(['code' => '143'], ['name' => 'Гериатр']);

    $cabinetsXlsx = writeXlsx([
        ['Субъект РФ', 'Наименование учреждения', 'Адрес учреждения'],
        ['Белгородская область', 'ОГБУЗ "Алексеевская ЦРБ"', 'Белгородская обл., г. Алексеевка, ул. Никольская, д.2'],
    ]);

    $outDir = sys_get_temp_dir().'/gerontology-out-'.Str::uuid();

    $this->artisan('gerontology:import', [
        '--dry-run' => true,
        '--cabinets' => $cabinetsXlsx,
        '--out-dir' => $outDir,
    ])->assertSuccessful();

    $plan = json_decode((string) file_get_contents($outDir.'/plan.json'), true);
    expect($plan['items'])->toHaveCount(1);

    $actions = $plan['items'][0]['actions'];
    expect($plan['items'][0]['match'])->toBeNull()
        ->and($actions)->toContain(['type' => 'create_organization', 'status' => 'pending_review', 'works_with_elderly' => true])
        ->and($actions)->toContain(['type' => 'attach_specialist_profile', 'specialist_profile_code' => '143']);
});
