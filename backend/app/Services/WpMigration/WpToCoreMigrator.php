<?php

namespace App\Services\WpMigration;

use App\Models\Article;
use App\Models\Organization;
use App\Models\Organizer;
use App\Models\Source;
use App\Models\Venue;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Str;

/**
 * Core migration service that transforms WordPress data into Navigator Core entities.
 *
 * Handles:
 * - Data transformation (coordinates inversion, contact parsing)
 * - Deduplication by INN/OGRN
 * - Creation of organizations, venues, organizers, pivot relationships
 * - Idempotent operations using updateOrCreate
 */
class WpToCoreMigrator
{
    private WpTaxonomyMapper $taxonomyMapper;

    private ?Source $legacySource = null;

    public function __construct(WpTaxonomyMapper $taxonomyMapper)
    {
        $this->taxonomyMapper = $taxonomyMapper;
    }

    /**
     * Initialize migration: create legacy source record.
     */
    public function initialize(): void
    {
        $this->legacySource = Source::firstOrCreate(
            ['base_url' => 'wordpress-legacy'],
            [
                'id' => (string) Str::uuid(),
                'name' => 'WordPress Legacy Database',
                'kind' => 'registry_sfr',
                'is_active' => false,
                'entry_points' => [],
            ]
        );
    }

    /**
     * Migrate a single WordPress listing to Core.
     *
     * @param  object  $wpListing  Raw WordPress listing data
     * @param  array<string, array<int>>  $taxonomies  Taxonomy term IDs from WP
     * @return array{organization: Organization, venue: ?Venue, created: bool}
     */
    public function migrateListing(object $wpListing, array $taxonomies): array
    {
        // Transform and clean data
        $organizationData = $this->transformOrganizationData($wpListing, $taxonomies);
        $venueData = $this->transformVenueData($wpListing);

        // Store contact data before removing temporary fields
        $contactPhones = $organizationData['_wp_contact_phones'] ?? [];
        $contactEmails = $organizationData['_wp_contact_emails'] ?? [];
        unset($organizationData['_wp_contact_phones'], $organizationData['_wp_contact_emails']);

        // Deduplicate: find existing organization by INN or OGRN
        $organization = $this->findOrCreateOrganization($organizationData);

        $wasCreated = $organization->wasRecentlyCreated;

        // Create venue if address/coordinates exist
        $venue = null;
        if (! empty($venueData['address_raw']) || isset($venueData['coordinates'])) {
            $venue = $this->createVenue($venueData, $organization->id);
        }

        // Create organizer (polymorphic link) with contact data
        $this->ensureOrganizer($organization, [
            '_wp_contact_phones' => $contactPhones,
            '_wp_contact_emails' => $contactEmails,
        ]);

        // Attach pivot relationships
        $this->attachTaxonomies($organization, $taxonomies);

        // Ensure Source records exist for organization site URLs and link to organizer (for Harvester)
        $organization->load('organizer');
        $this->ensureSourcesFromSiteUrls($organization);

        return [
            'organization' => $organization,
            'venue' => $venue,
            'created' => $wasCreated,
        ];
    }

    /**
     * Migrate a single listing with optional overrides (e.g. title for long WP titles).
     *
     * @param  array<string, mixed>  $overrides  Merged into organization data (e.g. ['title' => 'Short title'])
     * @return array{organization: Organization, venue: ?Venue, created: bool}
     */
    public function migrateListingWithOverrides(object $wpListing, array $taxonomies, array $overrides = []): array
    {
        $organizationData = array_merge(
            $this->transformOrganizationData($wpListing, $taxonomies),
            $overrides
        );
        $venueData = $this->transformVenueData($wpListing);

        $contactPhones = $organizationData['_wp_contact_phones'] ?? [];
        $contactEmails = $organizationData['_wp_contact_emails'] ?? [];
        unset($organizationData['_wp_contact_phones'], $organizationData['_wp_contact_emails']);

        $organization = $this->findOrCreateOrganization($organizationData);
        $wasCreated = $organization->wasRecentlyCreated;

        $venue = null;
        if (! empty($venueData['address_raw']) || isset($venueData['coordinates'])) {
            $venue = $this->createVenue($venueData, $organization->id);
        }

        $this->ensureOrganizer($organization, [
            '_wp_contact_phones' => $contactPhones,
            '_wp_contact_emails' => $contactEmails,
        ]);
        $this->attachTaxonomies($organization, $taxonomies);
        $organization->load('organizer');
        $this->ensureSourcesFromSiteUrls($organization);

        return [
            'organization' => $organization,
            'venue' => $venue,
            'created' => $wasCreated,
        ];
    }

    /**
     * Update an existing organization with data from a WP listing (e.g. 4425 replacing 3799).
     * Updates org fields, organizer contacts, first venue, and sources from listing.
     */
    public function updateOrganizationFromListing(Organization $organization, object $wpListing, array $taxonomies): void
    {
        $data = $this->transformOrganizationData($wpListing, $taxonomies);
        $contactPhones = $data['_wp_contact_phones'] ?? [];
        $contactEmails = $data['_wp_contact_emails'] ?? [];
        unset($data['_wp_contact_phones'], $data['_wp_contact_emails']);

        $trace = $organization->ai_source_trace ?? [];
        $trace[] = [
            'source_id' => $this->legacySource->id,
            'source_item_id' => "wp_post_{$wpListing->post_id}",
            'source_url' => null,
            'extracted_at' => now()->toIso8601String(),
            'confidence' => 1.0,
        ];
        $data['ai_source_trace'] = $trace;

        $organization->update([
            'title' => $data['title'],
            'description' => $data['description'],
            'inn' => $data['inn'],
            'site_urls' => $data['site_urls'],
            'ownership_type_id' => $data['ownership_type_id'],
            'ai_source_trace' => $trace,
        ]);

        $organizer = $organization->organizer;
        if ($organizer) {
            $organizer->update([
                'contact_phones' => array_values($contactPhones),
                'contact_emails' => array_values($contactEmails),
            ]);
        }

        $venueData = $this->transformVenueData($wpListing);
        $venue = $organization->venues()->first();
        if ($venue) {
            $venue->update([
                'address_raw' => $venueData['address_raw'],
                'region_iso' => $venueData['region_iso'],
            ]);
            if (! empty($venueData['_coordinates_sql'])) {
                DB::statement(
                    "UPDATE venues SET coordinates = {$venueData['_coordinates_sql']} WHERE id = ?",
                    [$venue->id]
                );
            }
        } elseif (! empty($venueData['address_raw']) || isset($venueData['coordinates'])) {
            $this->createVenue($venueData, $organization->id);
        }

        $this->attachTaxonomies($organization, $taxonomies);
        $organization->load('organizer');
        $this->ensureSourcesFromSiteUrls($organization);
    }

    /**
     * Create or update Source records for each unique base URL from organization site_urls.
     * Links each source to the organization's organizer so Harvester knows which organizer to update.
     *
     * @param  Organization  $organization  Organization with site_urls (JSONB) and organizer
     */
    private function ensureSourcesFromSiteUrls(Organization $organization): void
    {
        $siteUrls = $organization->site_urls ?? [];
        if (empty($siteUrls)) {
            return;
        }

        $organizer = $organization->organizer;
        $organizerId = $organizer?->id;

        $seen = [];
        foreach ($siteUrls as $url) {
            $baseUrl = $this->normalizeUrlToBase($url);
            if ($baseUrl === null || isset($seen[$baseUrl])) {
                continue;
            }
            $seen[$baseUrl] = true;

            try {
                $source = Source::firstOrCreate(
                    ['base_url' => $baseUrl],
                    [
                        'id' => (string) Str::uuid(),
                        'name' => parse_url($baseUrl, PHP_URL_HOST) ?: $baseUrl,
                        'kind' => 'org_website',
                        'entry_points' => [],
                        'is_active' => true,
                        'last_status' => 'pending',
                        'organizer_id' => $organizerId,
                    ]
                );

                // If source already existed without organizer_id, link it to this organizer
                if (! $source->wasRecentlyCreated && $organizerId !== null && $source->organizer_id === null) {
                    $source->update(['organizer_id' => $organizerId]);
                }
            } catch (\Throwable) {
                // Skip this URL on any DB/encoding error (e.g. invalid UTF-8 in base_url)
            }
        }
    }

    /**
     * Normalize URL to base (scheme + host) for use as Source.base_url.
     * Sanitizes to valid UTF-8 (WP data may contain broken encoding).
     *
     * @return string|null Base URL or null if invalid
     */
    private function normalizeUrlToBase(string $url): ?string
    {
        $url = trim($url);
        if ($url === '') {
            return null;
        }
        // Ensure valid UTF-8 for PostgreSQL (strip invalid sequences from WP data)
        $url = $this->sanitizeUtf8($url);
        if ($url === '' || ! str_contains($url, '://')) {
            return null;
        }
        $parsed = parse_url($url);
        if (empty($parsed['scheme']) || empty($parsed['host'])) {
            return null;
        }
        $scheme = strtolower($parsed['scheme']);
        $host = strtolower($parsed['host']);

        return $scheme.'://'.$host;
    }

    /**
     * Strip invalid UTF-8 byte sequences so string is safe for PostgreSQL UTF8 encoding.
     */
    private function sanitizeUtf8(string $value): string
    {
        if ($value === '') {
            return $value;
        }
        $converted = @iconv('UTF-8', 'UTF-8//IGNORE', $value);

        return $converted !== false ? $converted : '';
    }

    /**
     * Transform WordPress listing data into Organization attributes.
     *
     * @param  array<string, array<int>>  $taxonomies
     * @return array<string, mixed>
     */
    private function transformOrganizationData(object $wpListing, array $taxonomies): array
    {
        $inn = $this->cleanIdentifier($wpListing->hp_inn ?? null);
        $ogrn = $this->cleanIdentifier($wpListing->hp_ogrn ?? null);

        $data = [
            'title' => trim($wpListing->post_title ?? ''),
            'description' => $wpListing->post_content ?? '',
            'inn' => $inn,
            'ogrn' => $ogrn,
            'site_urls' => $this->parseArrayField($wpListing->hp_site ?? null),
            'ownership_type_id' => $this->taxonomyMapper->mapOwnershipType($taxonomies['ownership'] ?? []),
            'works_with_elderly' => true, // Default for Stage 0, requires verification in Stage 1
            'status' => 'approved', // Legacy data is pre-approved
            'ai_source_trace' => [
                [
                    'source_id' => $this->legacySource->id,
                    'source_item_id' => "wp_post_{$wpListing->post_id}",
                    'source_url' => null,
                    'extracted_at' => now()->toIso8601String(),
                    'confidence' => 1.0,
                ],
            ],
        ];

        // Store WP contact data for later extraction to organizer
        $data['_wp_contact_phones'] = $this->parseArrayField($wpListing->hp_phone ?? null);
        $data['_wp_contact_emails'] = $this->parseArrayField($wpListing->hp_email ?? null, validateEmail: true);

        return $data;
    }

    /**
     * Transform WordPress listing data into Venue attributes.
     *
     * @return array<string, mixed>
     */
    private function transformVenueData(object $wpListing): array
    {
        $addressRaw = trim($wpListing->hp_location ?? '');

        // CRITICAL: Invert coordinates (WP stores them swapped)
        // WP hp_latitude contains actual longitude value
        // WP hp_longitude contains actual latitude value
        $wpLatitude = $this->parseCoordinate($wpListing->hp_latitude ?? null);
        $wpLongitude = $this->parseCoordinate($wpListing->hp_longitude ?? null);

        // Swap them back to correct values
        $actualLatitude = $wpLongitude;  // WP longitude → Core latitude
        $actualLongitude = $wpLatitude;  // WP latitude → Core longitude

        $venueData = [
            'address_raw' => $addressRaw,
            'fias_id' => null, // Will be filled in Stage 1 via Dadata
            'kladr_id' => null,
            'region_iso' => $this->normalizeRegion($wpListing->hp_region ?? null),
        ];

        // Create PostGIS Point if coordinates exist
        // Store coordinates as string SQL for later raw update (can't use DB::raw in Eloquent create)
        if ($actualLatitude !== null && $actualLongitude !== null) {
            // PostGIS: ST_MakePoint(longitude, latitude)
            $venueData['_coordinates_sql'] = "ST_SetSRID(ST_MakePoint({$actualLongitude}, {$actualLatitude}), 4326)";
        }

        return $venueData;
    }

    /**
     * Find existing organization by INN/OGRN or create new one.
     *
     * @param  array<string, mixed>  $data
     */
    private function findOrCreateOrganization(array $data): Organization
    {
        $inn = $data['inn'] ?? null;
        $ogrn = $data['ogrn'] ?? null;

        // Build unique identifier for deduplication
        $uniqueAttributes = [];
        if ($inn) {
            $uniqueAttributes['inn'] = $inn;
        } elseif ($ogrn) {
            $uniqueAttributes['ogrn'] = $ogrn;
        }

        // If no identifiers, use title as fallback (less reliable)
        if (empty($uniqueAttributes)) {
            $uniqueAttributes['title'] = $data['title'];
        }

        return Organization::updateOrCreate($uniqueAttributes, $data);
    }

    /**
     * Create venue and link it to organization.
     *
     * Checks for existing venue with same address_raw for this organization
     * to prevent duplicates when multiple WP listings update the same organization.
     *
     * @param  array<string, mixed>  $venueData
     */
    private function createVenue(array $venueData, string $organizationId): ?Venue
    {
        // Check if venue with same address already exists for this organization
        if (! empty($venueData['address_raw'])) {
            $existingVenue = Venue::whereHas('organizations', function ($q) use ($organizationId) {
                $q->where('organizations.id', $organizationId);
            })
                ->where('address_raw', $venueData['address_raw'])
                ->first();

            if ($existingVenue) {
                // Venue already exists and is linked to this organization, return it without creating duplicate
                return $existingVenue;
            }
        }

        $coordinatesSql = $venueData['_coordinates_sql'] ?? null;
        unset($venueData['_coordinates_sql']);

        // Create venue without coordinates first
        $venue = Venue::create($venueData);

        // Update coordinates using raw SQL for PostGIS
        if ($coordinatesSql) {
            DB::statement(
                "UPDATE venues SET coordinates = {$coordinatesSql} WHERE id = ?",
                [$venue->id]
            );
        }

        // Link venue to organization via pivot
        $venue->organizations()->attach($organizationId, [
            'is_headquarters' => true, // First venue is assumed to be headquarters
        ]);

        return $venue;
    }

    /**
     * Ensure organizer (polymorphic) exists for organization.
     *
     * Uses exists() check instead of relationship to prevent duplicates
     * when organization is updated via updateOrCreate().
     *
     * @param  array<string, mixed>|null  $organizationData  Raw organization data with WP contacts
     */
    private function ensureOrganizer(Organization $organization, ?array $organizationData = null): void
    {
        // Use exists() for more reliable check when organization is updated
        if (Organizer::where('organizable_type', Organization::class)
            ->where('organizable_id', $organization->id)
            ->exists()) {
            return;
        }

        // Extract contact data from organization data if available
        $contactPhones = $organizationData['_wp_contact_phones'] ?? [];
        $contactEmails = $organizationData['_wp_contact_emails'] ?? [];

        Organizer::create([
            'organizable_type' => Organization::class,
            'organizable_id' => $organization->id,
            'contact_phones' => array_values($contactPhones),
            'contact_emails' => array_values($contactEmails),
            'status' => 'approved',
        ]);
    }

    /**
     * Attach taxonomy relationships via pivot tables.
     *
     * @param  array<string, array<int>>  $taxonomies
     */
    private function attachTaxonomies(Organization $organization, array $taxonomies): void
    {
        $categoryIds = $this->taxonomyMapper->mapCategories($taxonomies['categories'] ?? []);
        if (! empty($categoryIds)) {
            $organization->thematicCategories()->syncWithoutDetaching($categoryIds);
        }

        $typeIds = $this->taxonomyMapper->mapOrganizationTypes($taxonomies['types'] ?? []);
        $serviceTermIds = $taxonomies['services'] ?? [];
        $routed = $this->taxonomyMapper->routeServiceTerms($serviceTermIds);
        $organizationTypeIds = array_values(array_unique(array_merge($typeIds, $routed['organization_type_ids'])));
        if (! empty($organizationTypeIds)) {
            $organization->organizationTypes()->syncWithoutDetaching($organizationTypeIds);
        }

        if (! empty($routed['specialist_profile_ids'])) {
            $organization->specialistProfiles()->syncWithoutDetaching($routed['specialist_profile_ids']);
        }

        $serviceIds = $this->taxonomyMapper->mapServices($serviceTermIds);
        if (! empty($serviceIds)) {
            $organization->services()->syncWithoutDetaching($serviceIds);
        }
    }

    /**
     * Clean identifier (INN/OGRN): remove non-digit characters.
     */
    private function cleanIdentifier(?string $value): ?string
    {
        if (empty($value)) {
            return null;
        }

        $cleaned = preg_replace('/\D/', '', $value);

        return ! empty($cleaned) ? $cleaned : null;
    }

    /**
     * Parse comma-separated string into JSON array.
     *
     * @param  bool  $validateEmail  Whether to validate emails (for email fields)
     * @return array<string>
     */
    private function parseArrayField(?string $value, bool $validateEmail = false): array
    {
        if (empty($value)) {
            return [];
        }

        // Handle serialized PHP arrays (WordPress sometimes stores them this way)
        if (preg_match('/^a:\d+:/', $value)) {
            $unserialized = @unserialize($value);
            if (is_array($unserialized)) {
                $value = implode(',', array_filter($unserialized));
            }
        }

        $items = array_map('trim', explode(',', $value));
        $items = array_filter($items, function ($item) use ($validateEmail) {
            if (empty($item) || strtolower($item) === 'none') {
                return false;
            }

            if ($validateEmail) {
                return filter_var($item, FILTER_VALIDATE_EMAIL) !== false;
            }

            return true;
        });

        return array_values($items);
    }

    /**
     * Parse coordinate value to float.
     *
     * @param  string|float|null  $value
     */
    private function parseCoordinate($value): ?float
    {
        if ($value === null || $value === '') {
            return null;
        }

        $float = (float) $value;

        return ($float >= -180 && $float <= 180) ? $float : null;
    }

    /**
     * Normalize region identifier.
     *
     * @param  string|int|null  $value
     */
    private function normalizeRegion($value): ?string
    {
        if ($value === null || $value === '') {
            return null;
        }

        return (string) $value;
    }

    /**
     * Migrate WordPress post to Article.
     */
    public function migrateArticle(object $wpPost): ?Article
    {
        // Only migrate published posts
        if (($wpPost->post_status ?? '') !== 'publish') {
            return null;
        }

        return Article::updateOrCreate(
            [
                'slug' => $wpPost->post_name ?? Str::slug($wpPost->post_title ?? ''),
            ],
            [
                'title' => trim($wpPost->post_title ?? ''),
                'content' => $wpPost->post_content ?? '',
                'content_url' => null, // Can be set if permalink is available
                'status' => 'published',
                'published_at' => $wpPost->post_date ?? now(),
            ]
        );
    }
}
