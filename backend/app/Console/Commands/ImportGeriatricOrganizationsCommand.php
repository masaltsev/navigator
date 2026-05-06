<?php

namespace App\Console\Commands;

use App\Models\Organization;
use App\Models\OrganizationType;
use App\Models\Organizer;
use App\Models\SpecialistProfile;
use App\Models\Venue;
use App\Services\Dadata\DadataClient;
use App\Services\VenueAddressEnricher\VenueAddressEnricher;
use Illuminate\Console\Command;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\File;
use Illuminate\Support\Str;
use PhpOffice\PhpSpreadsheet\IOFactory;

class ImportGeriatricOrganizationsCommand extends Command
{
    protected $signature = 'gerontology:import
                            {--centers= : Path to "Гериатрические центры.xlsx"}
                            {--cabinets= : Path to "Гериатрические кабинеты.xlsx"}
                            {--limit=0 : Max rows per file (0 = no limit)}
                            {--use-dadata : Try to enrich INN/OGRN and geo via DaData}
                            {--out-dir= : Output dir for JSON plans (default: storage/app/gerontology-import/<timestamp>)}
                            {--stats-only : Only compute stats (do not include per-row items in JSON)}
                            {--dry-run : Do not write to DB, only generate JSON plans}
                            {--force : Apply changes to DB (required when not dry-run)}';

    protected $description = 'Import geriatric centers/cabinets from XLSX: match existing orgs; attach OrganizationType 140 and/or SpecialistProfile 143; create missing orgs + venues (optional DaData)';

    private const CODE_ORG_TYPE_GERIATRIC_DEPARTMENT = '140';

    private const CODE_SPECIALIST_PROFILE_GERIATRIC = '143';

    public function handle(): int
    {
        $dryRun = (bool) $this->option('dry-run');
        $force = (bool) $this->option('force');

        if (! $dryRun && ! $force) {
            $this->error('Use --dry-run to preview or --force to execute.');

            return self::FAILURE;
        }

        $centersPath = (string) ($this->option('centers') ?: '');
        $cabinetsPath = (string) ($this->option('cabinets') ?: '');
        $limit = (int) $this->option('limit');
        $useDadata = (bool) $this->option('use-dadata');
        $statsOnly = (bool) $this->option('stats-only');

        if ($centersPath === '' && $cabinetsPath === '') {
            $this->error('Provide at least one of: --centers=... or --cabinets=...');

            return self::FAILURE;
        }

        $orgTypeId = OrganizationType::query()->where('code', self::CODE_ORG_TYPE_GERIATRIC_DEPARTMENT)->value('id');
        $specialistProfileId = SpecialistProfile::query()->where('code', self::CODE_SPECIALIST_PROFILE_GERIATRIC)->value('id');
        if (! $orgTypeId || ! $specialistProfileId) {
            $this->error('Missing dictionary codes in DB: OrganizationType code=140 and/or SpecialistProfile code=143.');

            return self::FAILURE;
        }

        $outDir = (string) ($this->option('out-dir') ?: storage_path('app/gerontology-import/'.now()->format('Y-m-d__H-i-s')));
        File::ensureDirectoryExists($outDir);

        $venueEnricher = null;
        if ($useDadata) {
            if (! config('services.dadata.api_key')) {
                $this->warn('DADATA_API_KEY is not set; will run without DaData enrichment.');
                $useDadata = false;
            } else {
                $venueEnricher = new VenueAddressEnricher(DadataClient::fromConfig());
            }
        }

        $plans = [
            'generated_at' => now()->toAtomString(),
            'dry_run' => $dryRun,
            'inputs' => [
                'centers' => $centersPath ?: null,
                'cabinets' => $cabinetsPath ?: null,
            ],
            'items' => [],
            'stats' => [
                'total_rows' => 0,
                'matched_existing' => 0,
                'created_organizations' => 0,
                'planned_org_type_attach' => 0,
                'planned_specialist_profile_attach' => 0,
            ],
        ];

        $processFile = function (string $kind, string $path) use (
            $limit,
            $dryRun,
            $useDadata,
            $venueEnricher,
            $orgTypeId,
            $specialistProfileId,
            $statsOnly,
            &$plans
        ): void {
            if ($path === '') {
                return;
            }
            if (! is_readable($path)) {
                $this->warn("File not readable: {$path}");

                return;
            }

            $sheet = IOFactory::load($path)->getSheet(0);
            $rows = $sheet->toArray(null, true, true, true);

            $processed = 0;
            foreach ($rows as $idx => $row) {
                if ($idx === 1) {
                    continue; // header
                }

                $vals = array_filter($row, fn ($v) => $v !== null && trim((string) $v) !== '');
                if ($vals === []) {
                    continue;
                }

                $processed++;
                if ($limit > 0 && $processed > $limit) {
                    break;
                }

                $payload = $this->mapRowToPayload($kind, $row);
                if ($payload === null) {
                    continue;
                }

                $plans['stats']['total_rows']++;

                $match = $this->findExistingOrganization($payload['organization_title'], $payload['inn'], $payload['ogrn'], $payload['address_raw']);

                $itemPlan = [
                    'kind' => $kind,
                    'source' => [
                        'file' => $path,
                        'sheet' => $sheet->getTitle(),
                        'row' => $idx,
                    ],
                    'input' => $payload,
                    'match' => $match ? ['organization_id' => $match->id, 'title' => $match->title] : null,
                    'actions' => [],
                ];

                if ($match) {
                    $plans['stats']['matched_existing']++;

                    $hasOrgType = $match->organizationTypes()->where('organization_types.id', $orgTypeId)->exists();
                    $hasProfile = $match->specialistProfiles()->where('specialist_profiles.id', $specialistProfileId)->exists();

                    if ($kind === 'center' && ! $hasOrgType) {
                        $itemPlan['actions'][] = ['type' => 'attach_organization_type', 'organization_type_code' => self::CODE_ORG_TYPE_GERIATRIC_DEPARTMENT];
                        $plans['stats']['planned_org_type_attach']++;
                    }
                    if (! $hasProfile) {
                        $itemPlan['actions'][] = ['type' => 'attach_specialist_profile', 'specialist_profile_code' => self::CODE_SPECIALIST_PROFILE_GERIATRIC];
                        $plans['stats']['planned_specialist_profile_attach']++;
                    }

                    if (! $statsOnly) {
                        $plans['items'][] = $itemPlan;
                    }

                    continue;
                }

                $itemPlan['actions'][] = ['type' => 'create_organization', 'status' => 'pending_review', 'works_with_elderly' => true];
                $itemPlan['actions'][] = ['type' => 'create_venue', 'address_raw' => $payload['address_raw'], 'use_dadata' => $useDadata];

                if ($kind === 'center') {
                    $itemPlan['actions'][] = ['type' => 'attach_organization_type', 'organization_type_code' => self::CODE_ORG_TYPE_GERIATRIC_DEPARTMENT];
                    $plans['stats']['planned_org_type_attach']++;
                }
                $itemPlan['actions'][] = ['type' => 'attach_specialist_profile', 'specialist_profile_code' => self::CODE_SPECIALIST_PROFILE_GERIATRIC];
                $plans['stats']['planned_specialist_profile_attach']++;

                if (! $statsOnly) {
                    $plans['items'][] = $itemPlan;
                }

                if ($dryRun) {
                    continue;
                }

                DB::transaction(function () use ($payload, $kind, $useDadata, $venueEnricher, $orgTypeId, $specialistProfileId, &$plans) {
                    $org = Organization::create([
                        'title' => $payload['organization_title'],
                        'short_title' => null,
                        'description' => null,
                        'inn' => $payload['inn'],
                        'ogrn' => $payload['ogrn'],
                        'site_urls' => null,
                        'ownership_type_id' => null,
                        'coverage_level_id' => null,
                        'works_with_elderly' => true,
                        'ai_confidence_score' => null,
                        'ai_explanation' => null,
                        'ai_source_trace' => [
                            'kind' => 'gerontology_import',
                            'source' => $kind,
                            'region' => $payload['region'],
                        ],
                        'target_audience' => ['elderly'],
                        'vk_group_id' => null,
                        'ok_group_id' => null,
                        'status' => 'pending_review',
                        'source_reference' => $payload['source_reference'],
                    ]);

                    Organizer::updateOrCreate(
                        [
                            'organizable_type' => 'Organization',
                            'organizable_id' => $org->id,
                        ],
                        [
                            'contact_phones' => null,
                            'contact_emails' => null,
                            'status' => 'pending_review',
                        ]
                    );

                    $venue = Venue::firstOrCreate(
                        ['address_raw' => $payload['address_raw']],
                        ['address_raw' => $payload['address_raw']]
                    );

                    if ($useDadata && $venueEnricher) {
                        $result = $venueEnricher->enrichByAddress($venue);
                        if ($result->isSuccess()) {
                            $venue->fias_id = $result->fiasId;
                            $venue->fias_level = $result->fiasLevel;
                            $venue->city_fias_id = $result->cityFiasId;
                            $venue->kladr_id = $result->kladrId;
                            $venue->region_iso = $result->regionIso;
                            $venue->region_code = $result->regionCode;
                            $venue->save();
                            if ($result->lat !== null && $result->lon !== null) {
                                DB::update(
                                    'UPDATE venues SET coordinates = ST_SetSRID(ST_MakePoint(?, ?), 4326) WHERE id = ?',
                                    [$result->lon, $result->lat, $venue->id]
                                );
                            }
                        }
                    }

                    $org->venues()->syncWithoutDetaching([$venue->id => ['is_headquarters' => true]]);

                    if ($kind === 'center') {
                        $org->organizationTypes()->syncWithoutDetaching([$orgTypeId]);
                    }
                    $org->specialistProfiles()->syncWithoutDetaching([$specialistProfileId]);

                    $plans['stats']['created_organizations']++;
                });
            }
        };

        $processFile('center', $centersPath);
        $processFile('cabinet', $cabinetsPath);

        $outFile = rtrim($outDir, '/').'/plan.json';
        File::put($outFile, json_encode($plans, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE));

        $this->info('Done. Plan written to: '.$outFile);
        $this->info('Rows: '.$plans['stats']['total_rows'].', matched: '.$plans['stats']['matched_existing'].', created: '.$plans['stats']['created_organizations']);

        if ($dryRun) {
            $this->warn('Dry run — no changes.');
        }

        return self::SUCCESS;
    }

    /**
     * @param  array<string, mixed>  $row
     * @return array{region: string|null, organization_title: string, address_raw: string, inn: ?string, ogrn: ?string, source_reference: string}|null
     */
    private function mapRowToPayload(string $kind, array $row): ?array
    {
        if ($kind === 'center') {
            $region = $this->stringOrNull($row['A'] ?? null);
            $orgTitle = $this->stringOrNull($row['C'] ?? null) ?? $this->stringOrNull($row['B'] ?? null);
            $address = $this->stringOrNull($row['E'] ?? null);
        } else {
            $region = $this->stringOrNull($row['A'] ?? null);
            $orgTitle = $this->stringOrNull($row['B'] ?? null);
            $address = $this->stringOrNull($row['C'] ?? null);
        }

        if (! $orgTitle || ! $address) {
            return null;
        }

        return [
            'region' => $region,
            'organization_title' => $orgTitle,
            'address_raw' => $address,
            'inn' => null,
            'ogrn' => null,
            'source_reference' => 'gerontology:'.Str::slug($kind).':'.Str::uuid(),
        ];
    }

    private function stringOrNull(mixed $value): ?string
    {
        if (! is_string($value) && ! is_numeric($value)) {
            return null;
        }
        $s = trim((string) $value);

        return $s !== '' ? $s : null;
    }

    private function normalizeTitle(string $title): string
    {
        $t = mb_strtolower(trim($title));

        return preg_replace('/\s+/u', ' ', $t) ?? $t;
    }

    private function normalizeAddress(string $address): string
    {
        $t = trim($address);
        $t = preg_replace('/\s+/u', ' ', $t) ?? $t;

        return $t;
    }

    private function findExistingOrganization(string $title, ?string $inn, ?string $ogrn, string $addressRaw): ?Organization
    {
        $inn = $inn !== null ? trim($inn) : null;
        $ogrn = $ogrn !== null ? trim($ogrn) : null;

        if ($inn) {
            $byInn = Organization::query()->whereNull('deleted_at')->where('inn', $inn)->first();
            if ($byInn) {
                return $byInn;
            }
        }

        if ($ogrn) {
            $byOgrn = Organization::query()->whereNull('deleted_at')->where('ogrn', $ogrn)->first();
            if ($byOgrn) {
                return $byOgrn;
            }
        }

        $norm = $this->normalizeTitle($title);
        $byTitle = Organization::query()
            ->whereNull('deleted_at')
            ->whereRaw("lower(btrim(regexp_replace(title, '\\\\s+', ' ', 'g'))) = ?", [$norm])
            ->first();
        if ($byTitle) {
            return $byTitle;
        }

        $addr = $this->normalizeAddress($addressRaw);
        $orgId = DB::table('organization_venues as ov')
            ->join('venues as v', 'v.id', '=', 'ov.venue_id')
            ->whereNull('v.deleted_at')
            ->whereRaw("btrim(regexp_replace(v.address_raw, '\\\\s+', ' ', 'g')) = ?", [$addr])
            ->value('ov.organization_id');

        return $orgId ? Organization::query()->whereKey($orgId)->whereNull('deleted_at')->first() : null;
    }
}
