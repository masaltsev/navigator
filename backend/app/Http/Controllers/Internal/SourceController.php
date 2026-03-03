<?php

namespace App\Http\Controllers\Internal;

use App\Http\Controllers\Controller;
use App\Models\Organization;
use App\Models\Organizer;
use App\Models\Source;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Validator;
use Illuminate\Validation\ValidationException;

class SourceController extends Controller
{
    /**
     * List sources for an organizer.
     *
     * GET /api/internal/sources?organizer_id=UUID&kind=org_website&is_active=true
     */
    public function index(Request $request): JsonResponse
    {
        $validator = Validator::make($request->all(), [
            'organizer_id' => 'required|uuid|exists:organizers,id',
            'kind' => 'nullable|string|in:'.implode(',', Source::KINDS),
            'is_active' => 'nullable|boolean',
        ]);

        if ($validator->fails()) {
            throw ValidationException::withMessages($validator->errors()->toArray());
        }

        $query = Source::where('organizer_id', $request->query('organizer_id'))
            ->whereNull('deleted_at');

        if ($request->has('kind')) {
            $query->where('kind', $request->query('kind'));
        }

        if ($request->has('is_active')) {
            $query->where('is_active', filter_var($request->query('is_active'), FILTER_VALIDATE_BOOLEAN));
        }

        $sources = $query->orderBy('kind')->get([
            'id', 'organizer_id', 'name', 'kind', 'base_url', 'last_status', 'is_active', 'created_at',
            'last_crawled_at', 'crawl_period_days',
        ]);

        return response()->json(['data' => $sources]);
    }

    /**
     * Show a single source (for Harvester / patch_sources when only source_id is known).
     *
     * GET /api/internal/sources/{id}
     */
    public function show(string $id): JsonResponse
    {
        $source = Source::whereNull('deleted_at')->find($id);
        if (! $source) {
            return response()->json(['status' => 'error', 'message' => 'Source not found'], 404);
        }

        return response()->json([
            'data' => [
                'id' => $source->id,
                'organizer_id' => $source->organizer_id,
                'base_url' => $source->base_url,
                'kind' => $source->kind,
                'name' => $source->name,
            ],
        ]);
    }

    /**
     * List sources that are due for crawling (for Harvester / Laravel Scheduler).
     *
     * GET /api/internal/sources/due?limit=100
     * Criteria: is_active = true, deleted_at IS NULL, and
     * (last_crawled_at IS NULL OR last_crawled_at + crawl_period_days <= NOW()).
     * Returns fields needed for POST /harvest/run: id, base_url, organizer_id (as existing_entity_id).
     */
    public function due(Request $request): JsonResponse
    {
        $limit = min((int) $request->query('limit', 100), 500);

        $sources = Source::query()
            ->due()
            ->limit($limit)
            ->get(['id', 'base_url', 'organizer_id', 'kind', 'name']);

        $data = $sources->map(fn ($s) => [
            'id' => $s->id,
            'base_url' => $s->base_url,
            'organizer_id' => $s->organizer_id,
            'existing_entity_id' => $s->organizer_id,
            'source_item_id' => $s->base_url,
            'kind' => $s->kind,
        ]);

        return response()->json(['data' => $data]);
    }

    /**
     * Create a new source linked to an organizer.
     *
     * POST /api/internal/sources
     */
    public function store(Request $request): JsonResponse
    {
        $validator = Validator::make($request->all(), [
            'organizer_id' => 'required|uuid|exists:organizers,id',
            'base_url' => 'required|string|max:2048',
            'kind' => 'required|string|in:'.implode(',', Source::KINDS_CREATABLE),
            'name' => 'nullable|string|max:255',
            'priority' => 'nullable|integer|min:1|max:100',
            'crawl_period_days' => 'nullable|integer|min:1|max:365',
        ]);

        if ($validator->fails()) {
            throw ValidationException::withMessages($validator->errors()->toArray());
        }

        $data = $validator->validated();

        return DB::transaction(function () use ($data) {
            $organizerId = $data['organizer_id'];
            $baseUrl = $data['base_url'];
            $kind = $data['kind'];

            $existing = Source::where('organizer_id', $organizerId)
                ->where('base_url', $baseUrl)
                ->whereNull('deleted_at')
                ->first();

            if ($existing) {
                return response()->json([
                    'status' => 'exists',
                    'source_id' => $existing->id,
                    'message' => 'Source with this organizer_id and base_url already exists',
                ], 200);
            }

            $name = $data['name'] ?? preg_replace('#^https?://#', '', rtrim($baseUrl, '/'));

            $crawlPeriodDays = $data['crawl_period_days'] ?? ($kind === 'org_website' ? 30 : 7);
            $create = [
                'organizer_id' => $organizerId,
                'base_url' => $baseUrl,
                'kind' => $kind,
                'name' => $name,
                'priority' => $data['priority'] ?? 50,
                'crawl_period_days' => $crawlPeriodDays,
                'last_status' => 'pending',
                'is_active' => true,
                'entry_points' => [],
            ];
            if ($kind === 'org_website') {
                $create['last_crawled_at'] = now();
            }
            $source = Source::create($create);

            if ($kind === 'org_website') {
                $this->syncSiteUrls($organizerId, null, $baseUrl);
            }

            return response()->json([
                'status' => 'created',
                'source_id' => $source->id,
                'organizer_id' => $organizerId,
                'base_url' => $baseUrl,
                'kind' => $kind,
            ], 201);
        });
    }

    /**
     * Update an existing source.
     *
     * PATCH /api/internal/sources/{id}
     */
    public function update(Request $request, string $id): JsonResponse
    {
        $source = Source::find($id);
        if (! $source) {
            return response()->json(['status' => 'error', 'message' => 'Source not found'], 404);
        }

        $validator = Validator::make($request->all(), [
            'base_url' => 'nullable|string|max:2048',
            'name' => 'nullable|string|max:255',
            'kind' => 'nullable|string|in:'.implode(',', Source::KINDS),
            'last_status' => 'nullable|string|in:pending,success,error,skipped',
            'last_crawled_at' => 'nullable|date',
            'is_active' => 'nullable|boolean',
        ]);

        if ($validator->fails()) {
            throw ValidationException::withMessages($validator->errors()->toArray());
        }

        $data = $validator->validated();

        return DB::transaction(function () use ($source, $data) {
            $oldUrl = $source->base_url;
            $newUrl = $data['base_url'] ?? null;

            if ($newUrl && $newUrl !== $oldUrl && $source->organizer_id) {
                $conflict = Source::where('organizer_id', $source->organizer_id)
                    ->where('base_url', $newUrl)
                    ->where('id', '!=', $source->id)
                    ->whereNull('deleted_at')
                    ->first();

                if ($conflict) {
                    return response()->json([
                        'status' => 'conflict',
                        'message' => 'Another source with this base_url already exists for this organizer',
                        'conflicting_source_id' => $conflict->id,
                    ], 409);
                }
            }

            $updates = array_filter($data, fn ($v) => $v !== null);
            if (! empty($updates)) {
                $source->update($updates);
            }

            if ($newUrl && $newUrl !== $oldUrl && $source->organizer_id && $source->kind === 'org_website') {
                $this->syncSiteUrls($source->organizer_id, $oldUrl, $newUrl);
            }

            return response()->json([
                'status' => 'updated',
                'source_id' => $source->id,
                'old_url' => $oldUrl,
                'new_url' => $newUrl ?? $oldUrl,
            ]);
        });
    }

    /**
     * Keep organizations.site_urls in sync when a source URL changes.
     */
    private function syncSiteUrls(string $organizerId, ?string $oldUrl, string $newUrl): void
    {
        $organizer = Organizer::find($organizerId);
        if (! $organizer || ! ($organizer->organizable instanceof Organization)) {
            return;
        }

        $org = $organizer->organizable;
        $siteUrls = $org->site_urls ?? [];

        if ($oldUrl) {
            $siteUrls = array_values(array_filter($siteUrls, fn ($u) => $u !== $oldUrl));
        }

        if (! in_array($newUrl, $siteUrls, true)) {
            $siteUrls[] = $newUrl;
        }

        $org->update(['site_urls' => $siteUrls]);
    }
}
