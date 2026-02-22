<?php

namespace App\Console\Commands;

use App\Models\Organization;
use Illuminate\Console\Command;
use Illuminate\Support\Facades\DB;

/**
 * Проверка несоответствий между названием организации и местоположением venue.
 * Выявляет случаи, когда название указывает на один регион/город, а venue находится в другом.
 */
class CheckOrganizationVenueMismatches extends Command
{
    protected $signature = 'organizations:check-venue-mismatches
                            {--limit=50 : Максимальное количество результатов для вывода}
                            {--export= : Путь к файлу для экспорта результатов (JSON)}';

    protected $description = 'Проверка несоответствий между названием организации и местоположением venue';

    /**
     * Справочник: ключевые слова в названии → ожидаемый region_iso.
     * Фокус на региональных отделениях и областных организациях.
     */
    private const REGION_KEYWORDS = [
        'RU-MOW' => ['московск', 'москва'],
        'RU-SPE' => ['санкт-петербург', 'петербург'],
        'RU-SEV' => ['севастополь'],
        'RU-VLG' => ['вологодск', 'вологда'],
        'RU-ORE' => ['оренбургск', 'оренбург'],
        'RU-NEN' => ['ненецк', 'нарьян-мар'],
        'RU-LEN' => ['ленинградск'],
        'RU-ARK' => ['архангельск'],
        'RU-KYA' => ['красноярск'],
        'RU-ALT' => ['алтайск', 'барнаул'],
        'RU-AMU' => ['амурск', 'благовещенск'],
        'RU-BEL' => ['белгородск', 'белгород'],
    ];

    /**
     * Паттерны, которые указывают на региональное/областное отделение.
     */
    private const REGIONAL_PATTERNS = [
        'региональн',
        'областн',
        'краев',
        'республиканск',
    ];

    /**
     * Исключения: слова, которые могут быть частью названия района/улицы.
     */
    private const EXCLUDE_PATTERNS = [
        'московский район',
        'ленинградский район',
        'московская улица',
        'ленинградская улица',
    ];

    /**
     * Исключения для регионов: если в названии есть эти слова, это не тот регион.
     */
    private const REGION_EXCLUSIONS = [
        'RU-MOW' => ['московская область', 'московской области', 'московской обл', 'московская обл'],
        'RU-SPE' => ['ленинградская область', 'ленинградской области', 'ленинградской обл'],
    ];

    public function handle(): int
    {
        $limit = (int) $this->option('limit');
        $exportPath = $this->option('export');

        $this->info('Поиск несоответствий между названием организации и местоположением venue...');
        $this->newLine();

        $mismatches = $this->findMismatches($limit);

        if (empty($mismatches)) {
            $this->info('Несоответствий не найдено.');

            return self::SUCCESS;
        }

        $this->displayResults($mismatches);

        if ($exportPath) {
            $this->exportToFile($mismatches, $exportPath);
        }

        return self::SUCCESS;
    }

    /**
     * Найти несоответствия между названием и venue.
     *
     * @return array<int, array<string, mixed>>
     */
    private function findMismatches(int $limit): array
    {
        $mismatches = [];

        foreach (self::REGION_KEYWORDS as $expectedRegion => $keywords) {
            foreach ($keywords as $keyword) {
                // Ищем организации с региональными паттернами + ключевым словом региона
                $orgs = Organization::query()
                    ->where('status', 'approved')
                    ->where(function ($q) use ($keyword) {
                        foreach (self::REGIONAL_PATTERNS as $pattern) {
                            $q->orWhere(function ($q2) use ($pattern, $keyword) {
                                $q2->where('title', 'ILIKE', '%'.$pattern.'%')
                                    ->where('title', 'ILIKE', '%'.$keyword.'%');
                            });
                        }
                    })
                    ->whereHas('venues', function ($q) use ($expectedRegion) {
                        $q->where('region_iso', '!=', $expectedRegion)
                            ->whereNotNull('region_iso');
                    })
                    ->with(['venues' => function ($q) {
                        $q->limit(1);
                    }])
                    ->limit(20)
                    ->get(['id', 'title', 'inn', 'ogrn']);

                foreach ($orgs as $org) {
                    // Проверяем исключения (названия районов/улиц)
                    if ($this->shouldExclude($org->title)) {
                        continue;
                    }

                    // Проверяем исключения для регионов (например, "Московская область" != "Москва")
                    if ($this->shouldExcludeRegion($org->title, $expectedRegion)) {
                        continue;
                    }

                    $venue = $org->venues->first();
                    if (! $venue) {
                        continue;
                    }

                    $coords = $this->getVenueCoordinates($venue->id);
                    $distance = $coords ? $this->calculateDistanceToRegion($coords, $expectedRegion) : null;

                    $mismatches[] = [
                        'org_id' => $org->id,
                        'title' => $org->title,
                        'inn' => $org->inn,
                        'ogrn' => $org->ogrn,
                        'expected_region' => $expectedRegion,
                        'actual_region' => $venue->region_iso,
                        'venue_address' => $venue->address_raw,
                        'venue_coordinates' => $coords,
                        'distance_km' => $distance,
                    ];
                }
            }
        }

        // Удаляем дубликаты по org_id
        $unique = [];
        foreach ($mismatches as $m) {
            $unique[$m['org_id']] = $m;
        }

        return array_slice(array_values($unique), 0, $limit);
    }

    /**
     * Проверить, нужно ли исключить организацию (название района/улицы).
     */
    private function shouldExclude(string $title): bool
    {
        $titleLower = mb_strtolower($title);

        foreach (self::EXCLUDE_PATTERNS as $pattern) {
            if (mb_strpos($titleLower, $pattern) !== false) {
                return true;
            }
        }

        return false;
    }

    /**
     * Проверить, нужно ли исключить организацию для конкретного региона.
     * Например, "Московская область" не должна попадать под "Москва" (RU-MOW).
     */
    private function shouldExcludeRegion(string $title, string $regionIso): bool
    {
        if (! isset(self::REGION_EXCLUSIONS[$regionIso])) {
            return false;
        }

        $titleLower = mb_strtolower($title);

        foreach (self::REGION_EXCLUSIONS[$regionIso] as $exclusion) {
            if (mb_strpos($titleLower, $exclusion) !== false) {
                return true;
            }
        }

        return false;
    }

    /**
     * Получить координаты venue.
     *
     * @return array{lat: float, lng: float}|null
     */
    private function getVenueCoordinates(string $venueId): ?array
    {
        $row = DB::selectOne(
            'SELECT ST_Y(coordinates) as lat, ST_X(coordinates) as lng FROM venues WHERE id = ? AND coordinates IS NOT NULL',
            [$venueId]
        );

        if (! $row || $row->lat === null || $row->lng === null) {
            return null;
        }

        return [
            'lat' => (float) $row->lat,
            'lng' => (float) $row->lng,
        ];
    }

    /**
     * Вычислить примерное расстояние от координат до центра региона (для проверки).
     */
    private function calculateDistanceToRegion(array $coords, string $regionIso): ?float
    {
        // Центры некоторых регионов для проверки
        $regionCenters = [
            'RU-MOW' => ['lat' => 55.7558, 'lng' => 37.6173],
            'RU-SPE' => ['lat' => 59.9343, 'lng' => 30.3351],
            'RU-VLG' => ['lat' => 59.2181, 'lng' => 39.8887],
            'RU-ORE' => ['lat' => 51.7682, 'lng' => 55.0970],
            'RU-NEN' => ['lat' => 67.6398, 'lng' => 53.0529],
        ];

        if (! isset($regionCenters[$regionIso])) {
            return null;
        }

        $center = $regionCenters[$regionIso];
        $distance = DB::selectOne(
            'SELECT ST_Distance(ST_MakePoint(?, ?)::geography, ST_MakePoint(?, ?)::geography) / 1000 as dist_km',
            [$coords['lng'], $coords['lat'], $center['lng'], $center['lat']]
        );

        return $distance ? round((float) $distance->dist_km, 1) : null;
    }

    /**
     * Отобразить результаты в консоли.
     *
     * @param  array<int, array<string, mixed>>  $mismatches
     */
    private function displayResults(array $mismatches): void
    {
        $this->info('Найдено несоответствий: '.count($mismatches));
        $this->newLine();

        $headers = ['№', 'Организация', 'Ожидается', 'Фактически', 'Адрес venue'];
        $rows = [];

        foreach ($mismatches as $i => $m) {
            $rows[] = [
                $i + 1,
                mb_substr($m['title'], 0, 50).(mb_strlen($m['title']) > 50 ? '...' : ''),
                $m['expected_region'],
                $m['actual_region'],
                mb_substr($m['venue_address'] ?? '', 0, 40).(mb_strlen($m['venue_address'] ?? '') > 40 ? '...' : ''),
            ];
        }

        $this->table($headers, $rows);

        $this->newLine();
        $this->info('Для получения полных данных используйте --export=путь/к/файлу.json');
    }

    /**
     * Экспортировать результаты в файл.
     *
     * @param  array<int, array<string, mixed>>  $mismatches
     */
    private function exportToFile(array $mismatches, string $path): void
    {
        file_put_contents($path, json_encode($mismatches, JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT));
        $this->info("Результаты экспортированы в: {$path}");
    }
}
