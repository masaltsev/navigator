<?php

namespace App\Console\Commands;

use App\Models\Organization;
use App\Models\ThematicCategory;
use Illuminate\Console\Command;
use Illuminate\Support\Facades\Http;

/**
 * List organizations from Vologda that work with life situations
 * "Быт и социальная поддержка" (root code 4) and its child categories (18, 20).
 * Outputs structured cards to a report file.
 *
 * Use --via-api to fetch data via public API (list by thematic categories, then filter
 * by address containing "Вологда" and fetch full cards). API has no city-name filter.
 */
class ListVologdaBytOrganizations extends Command
{
    protected $signature = 'navigator:list-vologda-byt-organizations
                            {--output= : Path to output file (default: docs/reports/vologda_byt_organizations.json)}
                            {--format=json : Output format: json or markdown}
                            {--via-api : Fetch organizations via HTTP API instead of DB (filters by address client-side)}
                            {--api-url= : Base URL for API (default: APP_URL)}';

    protected $description = 'List organizations from Vologda in "Быт и социальная поддержка" (root + child categories), output structured cards';

    public function handle(): int
    {
        $root = ThematicCategory::where('code', '4')->first();
        if (! $root) {
            $this->error('Thematic category "Быт и социальная поддержка" (code 4) not found.');

            return self::FAILURE;
        }

        $childCodes = ['18', '20'];
        $children = ThematicCategory::whereIn('code', $childCodes)->pluck('id');
        $categoryIds = $children->push($root->id)->unique()->values();

        if ($this->option('via-api')) {
            $cards = $this->fetchCardsViaApi($categoryIds->all());
            $total = count($cards);
        } else {
            $organizations = Organization::query()
                ->where('status', 'approved')
                ->whereHas('thematicCategories', fn ($q) => $q->whereIn('thematic_categories.id', $categoryIds))
                ->whereHas('venues', fn ($q) => $q->where('address_raw', 'ilike', '%Вологда%'))
                ->with([
                    'organizationTypes',
                    'ownershipType',
                    'coverageLevel',
                    'thematicCategories',
                    'specialistProfiles',
                    'services',
                    'venues',
                ])
                ->orderBy('title')
                ->get();

            $this->info("Found {$organizations->count()} organizations in Vologda (Быт и социальная поддержка).");
            $cards = $organizations->map(fn (Organization $org) => $this->toCard($org))->all();
            $total = count($cards);
        }

        $this->info("Total cards: {$total}.");

        $outputPath = $this->option('output') ?: 'docs/reports/vologda_byt_organizations.json';
        $format = $this->option('format') ?: 'json';

        if ($format === 'markdown') {
            $content = $this->toMarkdown($cards, $total);
            $outputPath = preg_replace('/\.json$/', '.md', $outputPath);
        } else {
            $content = json_encode([
                'meta' => [
                    'source' => $this->option('via-api') ? 'Navigator Core API (via HTTP)' : 'Navigator Core API',
                    'filter' => [
                        'city' => 'Вологда',
                        'thematic_root' => 'Быт и социальная поддержка (code 4)',
                        'thematic_children' => ['Нуждаемость в постороннем уходе (18)', 'Одинокое проживание (20)'],
                    ],
                    'total' => $total,
                ],
                'data' => $cards,
            ], JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE);
        }

        $fullPath = base_path($outputPath);
        if (! is_dir(dirname($fullPath))) {
            mkdir(dirname($fullPath), 0755, true);
        }
        file_put_contents($fullPath, $content);

        $this->info("Written to {$outputPath}");

        return self::SUCCESS;
    }

    /**
     * Fetch organization cards via public API: list by thematic categories,
     * filter by address containing "Вологда", then load full detail per org.
     *
     * @param  array<int>  $categoryIds
     * @return array<int, array<string, mixed>>
     */
    private function fetchCardsViaApi(array $categoryIds): array
    {
        $baseUrl = rtrim($this->option('api-url') ?: config('app.url'), '/');
        $vologdaIds = [];

        $page = 1;
        $perPage = 100;
        do {
            $params = [
                'thematic_category_id' => $categoryIds,
                'per_page' => $perPage,
                'page' => $page,
            ];

            $response = Http::get("{$baseUrl}/api/v1/organizations", $params);
            if (! $response->successful()) {
                $this->error("API list request failed: {$response->status()}");

                return [];
            }

            $body = $response->json();
            $items = $body['data'] ?? [];
            foreach ($items as $item) {
                $address = $item['venue']['address'] ?? '';
                if (str_contains($address, 'Вологда')) {
                    $vologdaIds[$item['id']] = true;
                }
            }

            $total = (int) ($body['meta']['total'] ?? 0);
            $page++;
        } while ($page <= (int) ceil($total / $perPage) && $total > 0);

        $vologdaIds = array_keys($vologdaIds);
        $this->info('Via API: '.count($vologdaIds).' organizations in Vologda (Быт и социальная поддержка).');

        $cards = [];
        foreach ($vologdaIds as $id) {
            $detail = Http::get("{$baseUrl}/api/v1/organizations/{$id}");
            if (! $detail->successful()) {
                $this->warn("Skip org {$id}: detail request failed.");

                continue;
            }
            $cards[] = $this->cardFromApiDetail($detail->json('data'));
        }

        usort($cards, fn ($a, $b) => strcasecmp($a['title'] ?? '', $b['title'] ?? ''));

        return $cards;
    }

    /**
     * Map API organization detail (show) response to report card shape.
     *
     * @param  array<string, mixed>  $data
     * @return array<string, mixed>
     */
    private function cardFromApiDetail(array $data): array
    {
        $ownership = $data['ownership_type'] ?? null;

        return [
            'id' => $data['id'] ?? null,
            'type' => 'Organization',
            'title' => $data['title'] ?? '',
            'description' => $data['description'] ?? null,
            'inn' => $data['inn'] ?? null,
            'ogrn' => $data['ogrn'] ?? null,
            'site_urls' => $data['site_urls'] ?? [],
            'organization_types' => $data['organization_types'] ?? [],
            'ownership_type' => $ownership && ($ownership['id'] ?? null) ? $ownership : null,
            'coverage_level' => $data['coverage_level'] ?? null,
            'thematic_categories' => $data['thematic_categories'] ?? [],
            'specialist_profiles' => $data['specialist_profiles'] ?? [],
            'services' => $data['services'] ?? [],
            'venues' => array_map(fn ($v) => [
                'id' => $v['id'] ?? null,
                'address' => $v['address'] ?? '',
                'fias_id' => $v['fias_id'] ?? null,
                'is_headquarters' => $v['is_headquarters'] ?? false,
            ], $data['venues'] ?? []),
        ];
    }

    private function toCard(Organization $org): array
    {
        return [
            'id' => $org->id,
            'type' => 'Organization',
            'title' => $org->title,
            'description' => $org->description,
            'inn' => $org->inn,
            'ogrn' => $org->ogrn,
            'site_urls' => $org->site_urls,
            'organization_types' => $org->organizationTypes->map(fn ($t) => ['id' => $t->id, 'name' => $t->name])->all(),
            'ownership_type' => $org->ownershipType ? ['id' => $org->ownershipType->id, 'name' => $org->ownershipType->name] : null,
            'coverage_level' => $org->coverageLevel ? ['id' => $org->coverageLevel->id, 'name' => $org->coverageLevel->name] : null,
            'thematic_categories' => $org->thematicCategories->map(fn ($c) => ['id' => $c->id, 'name' => $c->name])->all(),
            'specialist_profiles' => $org->specialistProfiles->map(fn ($p) => ['id' => $p->id, 'name' => $p->name])->all(),
            'services' => $org->services->map(fn ($s) => ['id' => $s->id, 'name' => $s->name])->all(),
            'venues' => $org->venues->map(fn ($v) => [
                'id' => $v->id,
                'address' => $v->address_raw,
                'fias_id' => $v->fias_id,
                'is_headquarters' => $v->pivot->is_headquarters ?? false,
            ])->all(),
        ];
    }

    private function toMarkdown(array $cards, int $total): string
    {
        $lines = [
            '# Организации Вологды: Быт и социальная поддержка',
            '',
            'Жизненные ситуации: **Быт и социальная поддержка** (корневая категория) и дочерние: *Нуждаемость в постороннем уходе*, *Одинокое проживание*.',
            '',
            "**Всего организаций:** {$total}",
            '',
            '---',
            '',
        ];

        foreach ($cards as $i => $card) {
            $lines[] = '## '.($i + 1).'. '.($card['title'] ?? 'Без названия');
            $lines[] = '';
            $lines[] = '| Поле | Значение |';
            $lines[] = '|------|----------|';
            $lines[] = '| **ID** | `'.($card['id'] ?? '').'` |';
            $lines[] = '| **Описание** | '.($card['description'] ? mb_substr(strip_tags($card['description']), 0, 300).'...' : '—').' |';
            $lines[] = '| **ИНН** | '.($card['inn'] ?? '—').' |';
            $lines[] = '| **ОГРН** | '.($card['ogrn'] ?? '—').' |';
            $lines[] = '| **Сайты** | '.($card['site_urls'] ? implode(', ', $card['site_urls']) : '—').' |';
            $lines[] = '| **Типы организации** | '.$this->namesList($card['organization_types'] ?? []).' |';
            $lines[] = '| **Тематические категории** | '.$this->namesList($card['thematic_categories'] ?? []).' |';
            $lines[] = '| **Услуги** | '.$this->namesList($card['services'] ?? []).' |';
            $lines[] = '| **Площадки** | '.$this->venuesList($card['venues'] ?? []).' |';
            $lines[] = '';
        }

        return implode("\n", $lines);
    }

    private function namesList(array $items): string
    {
        $names = array_map(fn ($x) => $x['name'] ?? $x['title'] ?? '', $items);

        return implode(', ', array_filter($names)) ?: '—';
    }

    private function venuesList(array $venues): string
    {
        $parts = array_map(fn ($v) => ($v['address'] ?? $v['address_raw'] ?? '').(isset($v['is_headquarters']) && $v['is_headquarters'] ? ' (головной)' : ''), $venues);

        return implode('; ', array_filter($parts)) ?: '—';
    }
}
