<?php

namespace App\Http\Controllers\Internal;

use App\Http\Controllers\Controller;
use App\Models\CoverageLevel;
use App\Models\Event;
use App\Models\EventCategory;
use App\Models\InitiativeGroup;
use App\Models\Organization;
use App\Models\OrganizationType;
use App\Models\Organizer;
use App\Models\OwnershipType;
use App\Models\ProblemCategory;
use App\Models\Service;
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
     *
     * Expected JSON structure:
     * {
     *   "source_reference": "sfr_kld_12193_item_1",
     *   "entity_type": "Organization",
     *   "title": "...",
     *   "description": "...",
     *   "inn": "...",
     *   "ogrn": "...",
     *   "ai_metadata": {
     *     "decision": "accepted|rejected",
     *     "ai_explanation": "...",
     *     "ai_confidence_score": 0.98,
     *     "works_with_elderly": true,
     *     "ai_source_trace": [...]
     *   },
     *   "classification": {
     *     "organization_type_code": "44",
     *     "ownership_type_code": "164",
     *     "coverage_level_id": 2,
     *     "problem_category_codes": ["82"],
     *     "service_codes": ["81", "70"]
     *   },
     *   "venues": [...]
     * }
     */
    public function importOrganizer(Request $request): JsonResponse
    {
        $validator = Validator::make($request->all(), [
            'source_reference' => 'required|string',
            'entity_type' => 'required|string|in:Organization,InitiativeGroup,Individual',
            'title' => 'required|string|max:255',
            'description' => 'nullable|string',
            'inn' => 'nullable|string|max:12',
            'ogrn' => 'nullable|string|max:15',
            'ai_metadata' => 'required|array',
            'ai_metadata.decision' => 'required|string|in:accepted,rejected',
            'ai_metadata.ai_confidence_score' => 'required|numeric|min:0|max:1',
            'ai_metadata.works_with_elderly' => 'required|boolean',
            'ai_metadata.ai_explanation' => 'nullable|string',
            'ai_metadata.ai_source_trace' => 'nullable|array',
            'classification' => 'required|array',
            'classification.organization_type_code' => 'nullable|string',
            'classification.ownership_type_code' => 'nullable|string',
            'classification.coverage_level_id' => 'nullable|integer',
            'classification.problem_category_codes' => 'nullable|array',
            'classification.service_codes' => 'nullable|array',
            'venues' => 'nullable|array',
            'venues.*.address_raw' => 'required|string',
            'venues.*.fias_id' => 'nullable|string',
            'venues.*.geo_lat' => 'required|numeric',
            'venues.*.geo_lon' => 'required|numeric',
            'venues.*.is_headquarters' => 'nullable|boolean',
        ]);

        if ($validator->fails()) {
            throw ValidationException::withMessages($validator->errors()->toArray());
        }

        $data = $validator->validated();
        $aiMetadata = $data['ai_metadata'];
        $classification = $data['classification'];

        // TODO: Check if organizer already exists by source_reference (if tracking is implemented)

        return DB::transaction(function () use ($data, $aiMetadata, $classification) {
            // Determine status based on State Machine logic
            $status = $this->determineStatus($aiMetadata);

            // Create or update the entity based on entity_type
            $entity = match ($data['entity_type']) {
                'Organization' => $this->createOrUpdateOrganization($data, $classification, $aiMetadata, $status),
                'InitiativeGroup' => $this->createOrUpdateInitiativeGroup($data, $aiMetadata, $status),
                'Individual' => $this->createOrUpdateIndividual($data, $aiMetadata, $status),
            };

            // Create or update organizer (polymorphic)
            $organizer = $this->createOrUpdateOrganizer($entity, $aiMetadata, $status);

            // Process venues
            if (! empty($data['venues'])) {
                $this->processVenues($organizer, $data['venues'], $data['entity_type'] === 'Organization');
            }

            // Attach problem categories and services (for Organization)
            if ($data['entity_type'] === 'Organization' && ! empty($classification['problem_category_codes'])) {
                $this->attachProblemCategories($entity, $classification['problem_category_codes']);
            }

            if ($data['entity_type'] === 'Organization' && ! empty($classification['service_codes'])) {
                $this->attachServices($entity, $classification['service_codes']);
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
     *
     * Expected JSON structure similar to organizer, but with event-specific fields.
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
            'rrule_string' => 'nullable|string',
            'ai_metadata' => 'required|array',
            'ai_metadata.ai_confidence_score' => 'required|numeric|min:0|max:1',
            'ai_metadata.ai_explanation' => 'nullable|string',
            'ai_metadata.ai_source_trace' => 'nullable|array',
            'classification' => 'nullable|array',
            'classification.event_category_codes' => 'nullable|array',
            'venues' => 'nullable|array',
        ]);

        if ($validator->fails()) {
            throw ValidationException::withMessages($validator->errors()->toArray());
        }

        $data = $validator->validated();
        $aiMetadata = $data['ai_metadata'];

        return DB::transaction(function () use ($data, $aiMetadata) {
            $status = $this->determineStatus($aiMetadata);

            // Create or update event
            $event = Event::updateOrCreate(
                [
                    // TODO: Add unique identifier (e.g., source_reference or organizer_id + title hash)
                ],
                [
                    'organizer_id' => $data['organizer_id'],
                    'organization_id' => $this->getOrganizationIdFromOrganizer($data['organizer_id']),
                    'title' => $data['title'],
                    'description' => $data['description'] ?? null,
                    'attendance_mode' => $data['attendance_mode'],
                    'online_url' => $data['online_url'] ?? null,
                    'rrule_string' => $data['rrule_string'] ?? null,
                    'ai_confidence_score' => $aiMetadata['ai_confidence_score'],
                    'ai_explanation' => $aiMetadata['ai_explanation'] ?? null,
                    'ai_source_trace' => $aiMetadata['ai_source_trace'] ?? null,
                    'status' => $status,
                ]
            );

            // Attach event categories
            if (! empty($data['classification']['event_category_codes'])) {
                $this->attachEventCategories($event, $data['classification']['event_category_codes']);
            }

            // Process venues
            if (! empty($data['venues'])) {
                $this->processEventVenues($event, $data['venues']);
            }

            // TODO: Materialize event instances from rrule_string (background job)

            return response()->json([
                'status' => 'success',
                'event_id' => $event->id,
                'assigned_status' => $status,
            ], 201);
        });
    }

    /**
     * Batch import multiple organizers or events.
     *
     * Expected JSON structure:
     * {
     *   "items": [
     *     { ... organizer/event data ... },
     *     ...
     *   ]
     * }
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

        // TODO: Dispatch batch import job to queue for async processing
        // For now, return job_id placeholder

        return response()->json([
            'status' => 'accepted',
            'message' => 'Batch import queued',
            'job_id' => 'placeholder-job-id',
            'items_count' => count($request->input('items')),
        ], 202);
    }

    /**
     * Determine status based on State Machine logic from domain document.
     *
     * Rules:
     * - rejected: if decision is "rejected"
     * - approved: if decision is "accepted" AND confidence >= 0.85 AND works_with_elderly = true
     * - pending_review: if decision is "accepted" but confidence < 0.85
     * - draft: fallback (should not happen with proper AI pipeline)
     */
    private function determineStatus(array $aiMetadata): string
    {
        if (($aiMetadata['decision'] ?? null) === 'rejected') {
            return 'rejected';
        }

        if (($aiMetadata['decision'] ?? null) === 'accepted') {
            $confidence = $aiMetadata['ai_confidence_score'] ?? 0;
            $worksWithElderly = $aiMetadata['works_with_elderly'] ?? false;

            if ($confidence >= 0.85 && $worksWithElderly) {
                return 'approved'; // Smart Publish
            }

            return 'pending_review'; // Needs manual review
        }

        return 'draft'; // Fallback
    }

    /**
     * Create or update Organization entity.
     */
    private function createOrUpdateOrganization(
        array $data,
        array $classification,
        array $aiMetadata,
        string $status
    ): Organization {
        $organizationType = null;
        if (! empty($classification['organization_type_code'])) {
            $organizationType = OrganizationType::where('code', $classification['organization_type_code'])->first();
        }

        $ownershipType = null;
        if (! empty($classification['ownership_type_code'])) {
            $ownershipType = OwnershipType::where('code', $classification['ownership_type_code'])->first();
        }

        $coverageLevel = null;
        if (! empty($classification['coverage_level_id'])) {
            $coverageLevel = CoverageLevel::find($classification['coverage_level_id']);
        }

        return Organization::updateOrCreate(
            [
                // TODO: Use inn/ogrn or source_reference for uniqueness
                'inn' => $data['inn'] ?? null,
            ],
            [
                'title' => $data['title'],
                'description' => $data['description'] ?? null,
                'inn' => $data['inn'] ?? null,
                'ogrn' => $data['ogrn'] ?? null,
                'organization_type_id' => $organizationType?->id,
                'ownership_type_id' => $ownershipType?->id,
                'coverage_level_id' => $coverageLevel?->id,
                'works_with_elderly' => $aiMetadata['works_with_elderly'],
                'ai_confidence_score' => $aiMetadata['ai_confidence_score'],
                'ai_explanation' => $aiMetadata['ai_explanation'] ?? null,
                'ai_source_trace' => $aiMetadata['ai_source_trace'] ?? null,
                'status' => $status,
            ]
        );
    }

    /**
     * Create or update InitiativeGroup entity.
     */
    private function createOrUpdateInitiativeGroup(
        array $data,
        array $aiMetadata,
        string $status
    ): InitiativeGroup {
        return InitiativeGroup::updateOrCreate(
            [
                // TODO: Use source_reference or name hash for uniqueness
            ],
            [
                'name' => $data['title'],
                'description' => $data['description'] ?? null,
                'community_focus' => null, // TODO: Extract from data if available
                'established_date' => null, // TODO: Extract from data if available
                'works_with_elderly' => $aiMetadata['works_with_elderly'],
                'ai_confidence_score' => $aiMetadata['ai_confidence_score'],
                'ai_explanation' => $aiMetadata['ai_explanation'] ?? null,
                'ai_source_trace' => $aiMetadata['ai_source_trace'] ?? null,
                'status' => $status,
            ]
        );
    }

    /**
     * Create or update Individual entity.
     */
    private function createOrUpdateIndividual(
        array $data,
        array $aiMetadata,
        string $status
    ): \App\Models\Individual {
        // TODO: Implement Individual creation/update
        // Individual model has minimal fields: full_name, role, contact_email, contact_phone, consent_given
        throw new \RuntimeException('Individual import not yet implemented');
    }

    /**
     * Create or update Organizer (polymorphic router).
     */
    private function createOrUpdateOrganizer(
        $entity,
        array $aiMetadata,
        string $status
    ): Organizer {
        return Organizer::updateOrCreate(
            [
                'organizable_type' => get_class($entity),
                'organizable_id' => $entity->id,
            ],
            [
                'contact_phones' => null, // TODO: Extract from ai_source_trace or separate field
                'contact_emails' => null, // TODO: Extract from ai_source_trace or separate field
                'status' => $status,
            ]
        );
    }

    /**
     * Process venues and attach them to organizer/organization.
     */
    private function processVenues(Organizer $organizer, array $venues, bool $isOrganization): void
    {
        foreach ($venues as $venueData) {
            $venue = Venue::firstOrCreate(
                [
                    'fias_id' => $venueData['fias_id'] ?? null,
                ],
                [
                    'address_raw' => $venueData['address_raw'],
                    'kladr_id' => null, // TODO: Extract from Dadata if available
                    'region_iso' => null, // TODO: Extract from Dadata if available
                    // coordinates will be set via raw SQL (PostGIS)
                ]
            );

            // Set coordinates via raw SQL (PostGIS)
            if (isset($venueData['geo_lat'], $venueData['geo_lon'])) {
                DB::statement(
                    'UPDATE venues SET coordinates = ST_SetSRID(ST_MakePoint(?, ?), 4326) WHERE id = ?',
                    [$venueData['geo_lon'], $venueData['geo_lat'], $venue->id]
                );
            }

            // Attach to organization if applicable
            if ($isOrganization && $organizer->organizable instanceof Organization) {
                $organizer->organizable->venues()->syncWithoutDetaching([
                    $venue->id => [
                        'is_headquarters' => $venueData['is_headquarters'] ?? false,
                    ],
                ]);
            }
        }
    }

    /**
     * Process event venues.
     */
    private function processEventVenues(Event $event, array $venues): void
    {
        $venueIds = [];
        foreach ($venues as $venueData) {
            $venue = Venue::firstOrCreate(
                [
                    'fias_id' => $venueData['fias_id'] ?? null,
                ],
                [
                    'address_raw' => $venueData['address_raw'],
                ]
            );

            if (isset($venueData['geo_lat'], $venueData['geo_lon'])) {
                DB::statement(
                    'UPDATE venues SET coordinates = ST_SetSRID(ST_MakePoint(?, ?), 4326) WHERE id = ?',
                    [$venueData['geo_lon'], $venueData['geo_lat'], $venue->id]
                );
            }

            $venueIds[] = $venue->id;
        }

        $event->venues()->sync($venueIds);
    }

    /**
     * Attach problem categories to organization by codes.
     */
    private function attachProblemCategories(Organization $organization, array $codes): void
    {
        $categoryIds = ProblemCategory::whereIn('code', $codes)->pluck('id');
        $organization->problemCategories()->sync($categoryIds);
    }

    /**
     * Attach services to organization by codes.
     */
    private function attachServices(Organization $organization, array $codes): void
    {
        $serviceIds = Service::whereIn('code', $codes)->pluck('id');
        $organization->services()->sync($serviceIds);
    }

    /**
     * Attach event categories to event by codes.
     *
     * TODO: Unify identifier usage (code vs slug)
     * - Currently uses 'slug' for lookup, but 'code' field was added to event_categories table
     * - AI pipeline should be instructed to use either 'code' or 'slug' consistently
     * - Once decision is made, update this method to use the chosen identifier
     * - Consider: 'code' is more semantic for API/external systems, 'slug' is more URL-friendly
     */
    private function attachEventCategories(Event $event, array $codes): void
    {
        // TODO: EventCategory uses slug, not code - need to map or update schema
        $categoryIds = EventCategory::whereIn('slug', $codes)->pluck('id');
        $event->categories()->sync($categoryIds);
    }

    /**
     * Get organization_id from organizer (if organizer is an Organization).
     */
    private function getOrganizationIdFromOrganizer(string $organizerId): ?string
    {
        $organizer = Organizer::with('organizable')->find($organizerId);
        if ($organizer && $organizer->organizable instanceof Organization) {
            return $organizer->organizable->id;
        }

        return null;
    }
}
