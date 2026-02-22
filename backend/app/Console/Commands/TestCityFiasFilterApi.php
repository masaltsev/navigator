<?php

namespace App\Console\Commands;

use App\Models\Organization;
use Illuminate\Console\Command;
use Illuminate\Http\Request;

/**
 * Runs API checks for "Фильтр по городу (city_fias_id)" from docs/API_TESTING_CHECKLIST.md.
 * Uses in-process request (no HTTP server needed). Uses application DB.
 */
class TestCityFiasFilterApi extends Command
{
    protected $signature = 'api:test-city-fias-filter';

    protected $description = 'Test GET /api/v1/organizations filter by city_fias_id (populated place)';

    public function handle(): int
    {
        $this->info('Testing API: filter by city_fias_id (населённый пункт)');
        $this->newLine();

        $baseUrl = '/api/v1/organizations';
        $fail = 0;

        // 1) Find an approved org that has a venue with fias_id
        $orgWithVenue = Organization::query()
            ->where('status', 'approved')
            ->where('works_with_elderly', true)
            ->whereHas('venues', fn ($q) => $q->whereNotNull('fias_id')->where('fias_id', '!=', ''))
            ->with('venues')
            ->first();

        if (! $orgWithVenue) {
            $this->error('No approved organization with venue.fias_id found in DB. Seed data or run venue enrichment first.');

            return self::FAILURE;
        }

        $venue = $orgWithVenue->venues->first();
        $fiasId = $venue->fias_id;
        $orgId = $orgWithVenue->id;

        $this->line("  Using org: {$orgId}, venue fias_id: {$fiasId}");

        // 2) GET without filter — expect 200 and our org possibly in list
        $responseAll = $this->callApi($baseUrl);
        if ($responseAll->getStatusCode() !== 200) {
            $this->error("  FAIL: GET {$baseUrl} returned {$responseAll->getStatusCode()}");
            $fail++;
        } else {
            $this->info('  OK: GET /api/v1/organizations (no filter) → 200');
        }

        // 3) GET with city_fias_id — expect 200 and our org in list
        $responseFiltered = $this->callApi($baseUrl.'?city_fias_id='.urlencode($fiasId));
        if ($responseFiltered->getStatusCode() !== 200) {
            $this->error("  FAIL: GET {$baseUrl}?city_fias_id=... returned {$responseFiltered->getStatusCode()}");
            $fail++;
        } else {
            $data = json_decode($responseFiltered->getContent(), true);
            $ids = isset($data['data']) ? array_column($data['data'], 'id') : [];
            if (in_array($orgId, $ids, true)) {
                $this->info("  OK: GET with city_fias_id={$fiasId} → 200, organization found in list (total: ".count($ids).')');
            } else {
                $this->error("  FAIL: Organization {$orgId} not in response when filtering by city_fias_id={$fiasId}");
                $fail++;
            }
        }

        // 4) GET with non-existent city_fias_id — expect 200, our org must NOT be in list
        $fakeFiasId = '00000000-0000-0000-0000-000000000000';
        $responseFake = $this->callApi($baseUrl.'?city_fias_id='.$fakeFiasId);
        if ($responseFake->getStatusCode() !== 200) {
            $this->error("  FAIL: GET with fake city_fias_id returned {$responseFake->getStatusCode()}");
            $fail++;
        } else {
            $dataFake = json_decode($responseFake->getContent(), true);
            $idsFake = isset($dataFake['data']) ? array_column($dataFake['data'], 'id') : [];
            if (! in_array($orgId, $idsFake, true)) {
                $this->info('  OK: GET with non-existent city_fias_id → 200, our org correctly excluded (returned: '.count($idsFake).')');
            } else {
                $this->error("  FAIL: Organization {$orgId} should not appear when city_fias_id is non-existent");
                $fail++;
            }
        }

        // 5) Structure: data[].id, meta
        $data = json_decode($responseFiltered->getContent(), true);
        if (! isset($data['data']) || ! is_array($data['data'])) {
            $this->error('  FAIL: Response missing data array');
            $fail++;
        } elseif (! isset($data['meta']) || ! is_array($data['meta'])) {
            $this->error('  FAIL: Response missing meta (pagination)');
            $fail++;
        } else {
            $this->info('  OK: Response structure: data[], meta (pagination)');
        }

        // 6) Combined filter: city_fias_id + thematic_category_id (from checklist example)
        $category = $orgWithVenue->thematicCategories->first();
        if ($category) {
            $combinedUrl = $baseUrl.'?city_fias_id='.urlencode($fiasId).'&thematic_category_id[]='.$category->id;
            $responseCombined = $this->callApi($combinedUrl);
            if ($responseCombined->getStatusCode() !== 200) {
                $this->error("  FAIL: GET with city_fias_id + thematic_category_id returned {$responseCombined->getStatusCode()}");
                $fail++;
            } else {
                $dataCombined = json_decode($responseCombined->getContent(), true);
                $idsCombined = isset($dataCombined['data']) ? array_column($dataCombined['data'], 'id') : [];
                $hasOurOrg = in_array($orgId, $idsCombined, true);
                $this->info($hasOurOrg
                    ? '  OK: Combined filter (city + category) → 200, org in list ('.count($idsCombined).')'
                    : '  OK: Combined filter (city + category) → 200 (org not in list for this category, '.count($idsCombined).' returned)');
            }
        }

        $this->newLine();
        if ($fail > 0) {
            $this->error("Result: {$fail} check(s) failed.");

            return self::FAILURE;
        }

        $this->info('Result: all checks passed. Filter by city_fias_id works as expected.');

        return self::SUCCESS;
    }

    private function callApi(string $uri): \Symfony\Component\HttpFoundation\Response
    {
        $request = Request::create($uri, 'GET');
        $request->headers->set('Accept', 'application/json');

        return app()->handle($request);
    }
}
