<?php

namespace App\Http\Controllers\Internal;

use App\Http\Controllers\Controller;
use App\Models\CoverageLevel;
use App\Models\Event;
use App\Models\EventCategory;
use App\Models\EventInstance;
use App\Models\InitiativeGroup;
use App\Models\Organization;
use App\Models\OrganizationType;
use App\Models\Organizer;
use App\Models\OwnershipType;
use App\Models\Service;
use App\Models\SpecialistProfile;
use App\Models\SuggestedTaxonomyItem;
use App\Models\ThematicCategory;
use App\Models\Venue;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Validator;
use Illuminate\Validation\ValidationException;

class ImportController extends Controller
{
    /**
     * Import or update an organizer (Organization, InitiativeGroup, or Individual).
     */
    public function importOrganizer(Request $request): JsonResponse
    {
        $validator = Validator::make($request->all(), [
            'source_reference' => 'required|string',
            'entity_type' => 'required|string|in:Organization,InitiativeGroup,Individual',
            'title' => 'required|string|max:255',
            'short_title' => 'nullable|string|max:100',
            'description' => 'nullable|string',
            'inn' => 'nullable|string|max:12',
            'ogrn' => 'nullable|string|max:15',
            'ai_metadata' => 'required|array',
            'ai_metadata.decision' => 'required|string|in:accepted,rejected,needs_review',
            'ai_metadata.ai_confidence_score' => 'required|numeric|min:0|max:1',
            'ai_metadata.works_with_elderly' => 'required|boolean',
            'ai_metadata.ai_explanation' => 'nullable|string',
            'ai_metadata.ai_source_trace' => 'nullable|array',
            'classification' => 'required|array',
            'classification.organization_type_codes' => 'nullable|array',
            'classification.organization_type_codes.*' => 'string',
            'classification.ownership_type_code' => 'nullable|string',
            'classification.coverage_level_id' => 'nullable|integer',
            'classification.thematic_category_codes' => 'nullable|array',
            'classification.specialist_profile_codes' => 'nullable|array',
            'classification.service_codes' => 'nullable|array',
            'contacts' => 'nullable|array',
            'contacts.phones' => 'nullable|array',
            'contacts.phones.*' => 'string',
            'contacts.emails' => 'nullable|array',
            'contacts.emails.*' => 'string|email',
            'target_audience' => 'nullable|array',
            'target_audience.*' => 'string',
            'site_urls' => 'nullable|array',
            'site_urls.*' => 'string',
            'vk_group_url' => 'nullable|string|max:255',
            'ok_group_url' => 'nullable|string|max:255',
            'telegram_url' => 'nullable|string|max:255',
            'suggested_taxonomy' => 'nullable|array',
            'suggested_taxonomy.*.dictionary' => 'required_with:suggested_taxonomy|string',
            'suggested_taxonomy.*.term' => 'required_with:suggested_taxonomy|string',
            'suggested_taxonomy.*.reasoning' => 'nullable|string',
            'venues' => 'nullable|array',
            'venues.*.address_raw' => 'required|string',
            'venues.*.fias_id' => 'nullable|string',
            'venues.*.fias_level' => 'nullable|string|max:10',
            'venues.*.city_fias_id' => 'nullable|string|max:36',
            'venues.*.region_iso' => 'nullable|string|max:10',
            'venues.*.region_code' => 'nullable|string',
            'venues.*.kladr_id' => 'nullable|string',
            'venues.*.geo_lat' => 'nullable|numeric',
            'venues.*.geo_lon' => 'nullable|numeric',
            'venues.*.address_comment' => 'nullable|string|max:500',
            'venues.*.is_headquarters' => 'nullable|boolean',
        ]);

        if ($validator->fails()) {
            throw ValidationException::withMessages($validator->errors()->toArray());
        }

        $data = $validator->validated();
        $aiMetadata = $data['ai_metadata'];
        $classification = $data['classification'];

        return DB::transaction(function () use ($data, $aiMetadata, $classification) {
            $status = $this->determineStatus($aiMetadata);

            $entity = match ($data['entity_type']) {
                'Organization' => $this->createOrUpdateOrganization($data, $classification, $aiMetadata, $status),
                'InitiativeGroup' => $this->createOrUpdateInitiativeGroup($data, $aiMetadata, $status),
                'Individual' => $this->createOrUpdateIndividual($data, $aiMetadata, $status),
            };

            $organizer = $this->createOrUpdateOrganizer($entity, $data, $aiMetadata, $status);

            if (! empty($data['venues'])) {
                $this->processVenues($organizer, $data['venues'], $data['entity_type'] === 'Organization');
            }

            if ($data['entity_type'] === 'Organization') {
                $this->syncClassification($entity, $classification);

                if (! empty($data['suggested_taxonomy'])) {
                    $this->storeSuggestedTaxonomy($entity, $data['suggested_taxonomy'], $data['source_reference']);
                }
            }

            return response()->json([
                'status' => 'success',
                'organizer_id' => $organizer->id,
                'entity_id' => $entity->id,
                'entity_type' => $data['entity_type'],
                'assigned_status' => $status,
            ], 201);
        });
    }

    /**
     * Import or update an event.
     */
    public function importEvent(Request $request): JsonResponse
    {
        $validator = Validator::make($request->all(), [
            'source_reference' => 'required|string',
            'organizer_id' => 'required|uuid|exists:organizers,id',
            'title' => 'required|string|max:255',
            'description' => 'nullable|string',
            'attendance_mode' => 'required|string|in:offline,online,mixed',
            'online_url' => 'nullable|url',
            'event_page_url' => 'nullable|url',
            'rrule_string' => 'nullable|string',
            'start_datetime' => 'nullable|date',
            'end_datetime' => 'nullable|date|after_or_equal:start_datetime',
            'ai_metadata' => 'required|array',
            'ai_metadata.decision' => 'nullable|string|in:accepted,rejected,needs_review',
            'ai_metadata.ai_confidence_score' => 'required|numeric|min:0|max:1',
            'ai_metadata.works_with_elderly' => 'nullable|boolean',
            'ai_metadata.ai_explanation' => 'nullable|string',
            'ai_metadata.ai_source_trace' => 'nullable|array',
            'classification' => 'nullable|array',
            'classification.event_category_codes' => 'nullable|array',
            'classification.thematic_category_codes' => 'nullable|array',
            'classification.target_audience' => 'nullable|array',
            'venues' => 'nullable|array',
            'venues.*.address_raw' => 'nullable|string',
            'venues.*.venue_id' => 'nullable|uuid|exists:venues,id',
            'venues.*.fias_id' => 'nullable|string',
            'venues.*.fias_level' => 'nullable|string|max:10',
            'venues.*.city_fias_id' => 'nullable|string|max:36',
            'venues.*.region_iso' => 'nullable|string|max:10',
            'venues.*.region_code' => 'nullable|string',
            'venues.*.kladr_id' => 'nullable|string',
            'venues.*.geo_lat' => 'nullable|numeric',
            'venues.*.geo_lon' => 'nullable|numeric',
        ]);

        if ($validator->fails()) {
            throw ValidationException::withMessages($validator->errors()->toArray());
        }

        $data = $validator->validated();
        $aiMetadata = $data['ai_metadata'];

        return DB::transaction(function () use ($data, $aiMetadata) {
            $decision = $aiMetadata['decision'] ?? 'accepted';
            $status = $this->determineStatus(array_merge($aiMetadata, ['decision' => $decision]));

            $event = Event::updateOrCreate(
                [
                    'organizer_id' => $data['organizer_id'],
                    'source_reference' => $data['source_reference'],
                ],
                [
                    'organization_id' => $this->getOrganizationIdFromOrganizer($data['organizer_id']),
                    'title' => $data['title'],
                    'description' => $data['description'] ?? null,
                    'attendance_mode' => $data['attendance_mode'],
                    'online_url' => $data['online_url'] ?? null,
                    'event_page_url' => $data['event_page_url'] ?? null,
                    'rrule_string' => $data['rrule_string'] ?? null,
                    'target_audience' => $data['classification']['target_audience'] ?? null,
                    'ai_confidence_score' => $aiMetadata['ai_confidence_score'],
                    'ai_explanation' => $aiMetadata['ai_explanation'] ?? null,
                    'ai_source_trace' => $aiMetadata['ai_source_trace'] ?? null,
                    'status' => $status,
                ]
            );

            if (! empty($data['classification']['event_category_codes'])) {
                $this->attachEventCategories($event, $data['classification']['event_category_codes']);
            }

            if (! empty($data['venues'])) {
                $this->processEventVenues($event, $data['venues']);
            }

            $instancesCreated = 0;
            if (! empty($data['start_datetime']) && ! empty($data['end_datetime'])) {
                $event->instances()->firstOrCreate(
                    [
                        'start_datetime' => $data['start_datetime'],
                        'end_datetime' => $data['end_datetime'],
                    ],
                    [
                        'status' => 'scheduled',
                    ]
                );
                $instancesCreated = 1;
            }

            return response()->json([
                'status' => 'success',
                'event_id' => $event->id,
                'assigned_status' => $status,
                'instances_created' => $instancesCreated,
            ], 201);
        });
    }

    /**
     * Batch import multiple organizers or events.
     */
    public function importBatch(Request $request): JsonResponse
    {
        $validator = Validator::make($request->all(), [
            'items' => 'required|array|min:1|max:100',
            'items.*' => 'required|array',
        ]);

        if ($validator->fails()) {
            throw ValidationException::withMessages($validator->errors()->toArray());
        }

        return response()->json([
            'status' => 'accepted',
            'message' => 'Batch import queued',
            'job_id' => 'placeholder-job-id',
            'items_count' => count($request->input('items')),
        ], 202);
    }

    /**
     * State Machine: decision + confidence + works_with_elderly → status.
     *
     * rejected → rejected
     * needs_review → pending_review
     * accepted + confidence >= 0.85 + works_with_elderly → approved (Smart Publish)
     * accepted + low confidence or !works_with_elderly → pending_review
     * fallback → draft
     */
    private function determineStatus(array $aiMetadata): string
    {
        $decision = $aiMetadata['decision'] ?? null;

        if ($decision === 'rejected') {
            return 'rejected';
        }

        if ($decision === 'needs_review') {
            return 'pending_review';
        }

        if ($decision === 'accepted') {
            $confidence = $aiMetadata['ai_confidence_score'] ?? 0;
            $worksWithElderly = $aiMetadata['works_with_elderly'] ?? false;

            if ($confidence >= 0.85 && $worksWithElderly) {
                return 'approved';
            }

            return 'pending_review';
        }

        return 'draft';
    }

    /**
     * Deduplication strategy (fallback chain):
     * 1. source_reference (unique per AI pipeline run)
     * 2. inn (if non-null — legal entity match)
     * 3. title (fuzzy last resort — may be refined later)
     */
    private function createOrUpdateOrganization(
        array $data,
        array $classification,
        array $aiMetadata,
        string $status
    ): Organization {
        $ownershipType = null;
        if (! empty($classification['ownership_type_code'])) {
            $ownershipType = OwnershipType::where('code', $classification['ownership_type_code'])->first();
        }

        $coverageLevel = null;
        if (! empty($classification['coverage_level_id'])) {
            $coverageLevel = CoverageLevel::find($classification['coverage_level_id']);
        }

        $attributes = [
            'title' => $data['title'],
            'short_title' => $data['short_title'] ?? null,
            'description' => $data['description'] ?? null,
            'inn' => $data['inn'] ?? null,
            'ogrn' => $data['ogrn'] ?? null,
            'ownership_type_id' => $ownershipType?->id,
            'coverage_level_id' => $coverageLevel?->id,
            'works_with_elderly' => $aiMetadata['works_with_elderly'],
            'ai_confidence_score' => $aiMetadata['ai_confidence_score'],
            'ai_explanation' => $aiMetadata['ai_explanation'] ?? null,
            'ai_source_trace' => $aiMetadata['ai_source_trace'] ?? null,
            'site_urls' => $data['site_urls'] ?? null,
            'target_audience' => $data['target_audience'] ?? null,
            'vk_group_id' => $this->extractVkGroupId($data['vk_group_url'] ?? null),
            'source_reference' => $data['source_reference'],
            'status' => $status,
        ];

        $existing = $this->findExistingOrganization($data['source_reference'], $data['inn'] ?? null);

        if ($existing) {
            $existing->update($attributes);

            return $existing;
        }

        return Organization::create($attributes);
    }

    /**
     * Fallback chain lookup: source_reference → inn → null (create new).
     */
    private function findExistingOrganization(string $sourceReference, ?string $inn): ?Organization
    {
        $bySource = Organization::where('source_reference', $sourceReference)->first();
        if ($bySource) {
            return $bySource;
        }

        if ($inn) {
            $byInn = Organization::where('inn', $inn)->first();
            if ($byInn) {
                return $byInn;
            }
        }

        return null;
    }

    private function createOrUpdateInitiativeGroup(
        array $data,
        array $aiMetadata,
        string $status
    ): InitiativeGroup {
        return InitiativeGroup::updateOrCreate(
            ['name' => $data['title']],
            [
                'description' => $data['description'] ?? null,
                'community_focus' => null,
                'established_date' => null,
                'works_with_elderly' => $aiMetadata['works_with_elderly'],
                'ai_confidence_score' => $aiMetadata['ai_confidence_score'],
                'ai_explanation' => $aiMetadata['ai_explanation'] ?? null,
                'ai_source_trace' => $aiMetadata['ai_source_trace'] ?? null,
                'status' => $status,
            ]
        );
    }

    private function createOrUpdateIndividual(
        array $data,
        array $aiMetadata,
        string $status
    ): \App\Models\Individual {
        throw new \RuntimeException('Individual import not yet implemented');
    }

    private function createOrUpdateOrganizer(
        $entity,
        array $data,
        array $aiMetadata,
        string $status
    ): Organizer {
        $contacts = $data['contacts'] ?? [];

        return Organizer::updateOrCreate(
            [
                'organizable_type' => $entity->getMorphClass(),
                'organizable_id' => $entity->id,
            ],
            [
                'contact_phones' => ! empty($contacts['phones']) ? $contacts['phones'] : null,
                'contact_emails' => ! empty($contacts['emails']) ? $contacts['emails'] : null,
                'status' => $status,
            ]
        );
    }

    /**
     * Create or match venues and attach to organization.
     * Now persists fias_level, city_fias_id, region_iso, region_code, kladr_id from Harvester.
     *
     * If the organization already has venues attached, we skip adding from payload to avoid
     * duplicates from LLM (existing venues are assumed verified/Dadata-linked). New orgs get
     * venues from the import payload (with optional Dadata geo).
     */
    private function processVenues(Organizer $organizer, array $venues, bool $isOrganization): void
    {
        if (! $isOrganization || ! $organizer->organizable instanceof Organization) {
            return;
        }

        $org = $organizer->organizable;
        if ($org->venues()->exists()) {
            return;
        }

        foreach ($venues as $venueData) {
            $venue = $this->resolveVenue($venueData);
            $org->venues()->syncWithoutDetaching([
                $venue->id => [
                    'is_headquarters' => $venueData['is_headquarters'] ?? false,
                ],
            ]);
        }
    }

    private function processEventVenues(Event $event, array $venues): void
    {
        $venueIds = [];
        foreach ($venues as $venueData) {
            if (! empty($venueData['venue_id'])) {
                $venueIds[] = $venueData['venue_id'];

                continue;
            }

            if (empty($venueData['address_raw'])) {
                continue;
            }

            $venue = $this->resolveVenue($venueData);
            $venueIds[] = $venue->id;
        }

        $event->venues()->sync($venueIds);
    }

    /**
     * Find existing venue by fias_id or address_raw; create if not found.
     * Updates geo fields (fias_level, city_fias_id, region_iso, region_code, kladr_id, coordinates).
     */
    private function resolveVenue(array $venueData): Venue
    {
        $matchKey = ! empty($venueData['fias_id'])
            ? ['fias_id' => $venueData['fias_id']]
            : ['address_raw' => $venueData['address_raw']];

        $venue = Venue::firstOrCreate(
            $matchKey,
            ['address_raw' => $venueData['address_raw']]
        );

        $geoUpdates = array_filter([
            'fias_id' => $venueData['fias_id'] ?? null,
            'fias_level' => $venueData['fias_level'] ?? null,
            'city_fias_id' => $venueData['city_fias_id'] ?? null,
            'region_iso' => $venueData['region_iso'] ?? null,
            'region_code' => $venueData['region_code'] ?? null,
            'kladr_id' => $venueData['kladr_id'] ?? null,
        ], fn ($v) => $v !== null);

        if ($geoUpdates) {
            $venue->update($geoUpdates);
        }

        if (isset($venueData['geo_lat'], $venueData['geo_lon'])) {
            DB::statement(
                'UPDATE venues SET coordinates = ST_SetSRID(ST_MakePoint(?, ?), 4326) WHERE id = ?',
                [$venueData['geo_lon'], $venueData['geo_lat'], $venue->id]
            );
        }

        return $venue;
    }

    /**
     * Extract numeric VK group ID from URL.
     * Handles: https://vk.com/club123456, https://vk.com/public123456, vk.com/some_group_name
     * Returns null if URL is empty or ID cannot be extracted.
     */
    private function extractVkGroupId(?string $url): ?int
    {
        if (empty($url)) {
            return null;
        }

        if (preg_match('/(?:club|public)(\d+)/i', $url, $matches)) {
            return (int) $matches[1];
        }

        return null;
    }

    /**
     * Persist AI-suggested taxonomy terms that don't match existing dictionaries.
     *
     * Expected format: [{"dictionary": "services", "term": "Танцевальная терапия", "reasoning": "..."}]
     */
    private function storeSuggestedTaxonomy(Organization $entity, array $suggestions, string $sourceReference): void
    {
        foreach ($suggestions as $suggestion) {
            if (empty($suggestion['dictionary']) || empty($suggestion['term'])) {
                continue;
            }

            SuggestedTaxonomyItem::updateOrCreate(
                [
                    'organization_id' => $entity->id,
                    'dictionary_type' => $suggestion['dictionary'],
                    'suggested_name' => $suggestion['term'],
                ],
                [
                    'source_reference' => $sourceReference,
                    'ai_reasoning' => $suggestion['reasoning'] ?? null,
                    'status' => 'pending',
                ]
            );
        }
    }

    private function syncClassification(Organization $entity, array $classification): void
    {
        if (! empty($classification['thematic_category_codes'])) {
            $ids = ThematicCategory::whereIn('code', $classification['thematic_category_codes'])->pluck('id');
            $entity->thematicCategories()->sync($ids);
        }

        if (! empty($classification['organization_type_codes'])) {
            $ids = OrganizationType::whereIn('code', $classification['organization_type_codes'])->pluck('id');
            $entity->organizationTypes()->sync($ids);
        }

        if (! empty($classification['specialist_profile_codes'])) {
            $ids = SpecialistProfile::whereIn('code', $classification['specialist_profile_codes'])->pluck('id');
            $entity->specialistProfiles()->sync($ids);
        }

        if (! empty($classification['service_codes'])) {
            $ids = Service::whereIn('code', $classification['service_codes'])->pluck('id');
            $entity->services()->sync($ids);
        }
    }

    private function attachEventCategories(Event $event, array $codes): void
    {
        $categoryIds = EventCategory::where(function ($query) use ($codes) {
            $query->whereIn('code', $codes)->orWhereIn('slug', $codes);
        })->pluck('id');

        $event->categories()->sync($categoryIds);
    }

    /**
     * Lookup organizer by source_reference, INN, or source_id.
     * Used by Harvester to resolve existing_entity_id before import.
     *
     * GET /api/internal/organizers?source_reference=X
     * GET /api/internal/organizers?inn=Y
     * GET /api/internal/organizers?source_id=Z  (finds organizer linked to a source)
     */
    public function lookupOrganizer(Request $request): JsonResponse
    {
        $sourceReference = $request->query('source_reference');
        $inn = $request->query('inn');
        $sourceId = $request->query('source_id');

        $organizer = null;

        if ($sourceReference) {
            $org = Organization::where('source_reference', $sourceReference)->first();
            $organizer = $org?->organizer;
        }

        if (! $organizer && $inn) {
            $org = Organization::where('inn', $inn)->first();
            $organizer = $org?->organizer;
        }

        if (! $organizer && $sourceId) {
            $source = \App\Models\Source::find($sourceId);
            $organizer = $source?->organizer;
        }

        if (! $organizer) {
            return response()->json(['data' => null], 404);
        }

        return response()->json([
            'data' => [
                'organizer_id' => $organizer->id,
                'entity_type' => class_basename($organizer->organizable_type),
                'entity_id' => $organizer->organizable_id,
                'status' => $organizer->status,
            ],
        ]);
    }

    /**
     * Return paginated list of organizations that have no active sources.
     *
     * GET /api/internal/organizations/without-sources?page=1&per_page=100
     */
    public function organizationsWithoutSources(Request $request): JsonResponse
    {
        $perPage = min((int) $request->query('per_page', 100), 500);

        $query = Organization::query()
            ->whereNull('organizations.deleted_at')
            ->whereNotExists(function ($sub) {
                $sub->select(DB::raw(1))
                    ->from('organizers')
                    ->join('sources', 'sources.organizer_id', '=', 'organizers.id')
                    ->whereColumn('organizers.organizable_id', 'organizations.id')
                    ->where('organizers.organizable_type', 'like', '%Organization%')
                    ->whereNull('sources.deleted_at')
                    ->where('sources.is_active', true);
            })
            ->join('organizers', function ($join) {
                $join->on('organizers.organizable_id', '=', 'organizations.id')
                    ->where('organizers.organizable_type', 'like', '%Organization%');
            })
            ->select([
                'organizations.id as org_id',
                'organizers.id as organizer_id',
                'organizations.title',
                'organizations.inn',
            ])
            ->orderBy('organizations.title');

        $paginated = $query->paginate($perPage);

        return response()->json([
            'data' => $paginated->items(),
            'meta' => [
                'total' => $paginated->total(),
                'page' => $paginated->currentPage(),
                'per_page' => $paginated->perPage(),
                'last_page' => $paginated->lastPage(),
            ],
        ]);
    }

    private function getOrganizationIdFromOrganizer(string $organizerId): ?string
    {
        $organizer = Organizer::with('organizable')->find($organizerId);
        if ($organizer && $organizer->organizable instanceof Organization) {
            return $organizer->organizable->id;
        }

        return null;
    }
}
