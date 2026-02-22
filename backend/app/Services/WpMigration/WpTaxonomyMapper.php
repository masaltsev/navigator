<?php

namespace App\Services\WpMigration;

use App\Models\OrganizationType;
use App\Models\OwnershipType;
use App\Models\Service;
use App\Models\SpecialistProfile;
use App\Models\ThematicCategory;
use Illuminate\Support\Collection;

/**
 * Maps WordPress taxonomy term IDs to Navigator Core dictionary records.
 *
 * WordPress stores taxonomy relationships using numeric term IDs.
 * These term IDs correspond to the `code` field in Core dictionaries
 * (not the auto-increment `id`). Mapping rules:
 * - hp_listing_category → thematic_categories (19→7, 13→8; 21,22,23 are in services only).
 * - hp_listing_type → organization_types (pivot).
 * - hp_listing_service → route by code to organization_types, specialist_profiles, or services (pivots).
 */
class WpTaxonomyMapper
{
    /** @var array<string, Collection<string, \Illuminate\Database\Eloquent\Model>>> */
    private array $cache = [];

    /** WP category term_id 19 → Core thematic_category code 7 */
    private const CATEGORY_MAP_19_TO_7 = 19;

    /** WP category term_id 13 → Core thematic_category code 8 */
    private const CATEGORY_MAP_13_TO_8 = 13;

    /** Codes that moved from categories to services (do not attach as thematic). */
    private const CATEGORY_CODES_IN_SERVICES = [21, 22, 23];

    /**
     * Map WordPress category term IDs to ThematicCategory IDs.
     * Applies 19→7, 13→8; excludes 21, 22, 23 (they are in services).
     *
     * @param  array<int>  $wpTermIds
     * @return array<int> Core thematic_category IDs
     */
    public function mapCategories(array $wpTermIds): array
    {
        if (empty($wpTermIds)) {
            return [];
        }

        $categories = $this->getCachedDictionary('thematic_categories', fn () => ThematicCategory::all()->keyBy('code'));

        $mappedIds = [];
        foreach ($wpTermIds as $wpTermId) {
            $code = (string) $wpTermId;
            if (in_array((int) $wpTermId, self::CATEGORY_CODES_IN_SERVICES, true)) {
                continue;
            }
            if ($wpTermId === self::CATEGORY_MAP_19_TO_7) {
                $code = '7';
            } elseif ($wpTermId === self::CATEGORY_MAP_13_TO_8) {
                $code = '8';
            }
            if ($categories->has($code)) {
                $mappedIds[] = $categories->get($code)->id;
            }
        }

        return array_values(array_unique($mappedIds));
    }

    /**
     * Map WordPress type term IDs to OrganizationType IDs (for pivot).
     *
     * @param  array<int>  $wpTermIds
     * @return array<int> Core organization_type IDs
     */
    public function mapOrganizationTypes(array $wpTermIds): array
    {
        if (empty($wpTermIds)) {
            return [];
        }

        $types = $this->getCachedDictionary('organization_types', fn () => OrganizationType::all()->keyBy('code'));

        $ids = [];
        foreach ($wpTermIds as $wpTermId) {
            $code = (string) $wpTermId;
            if ($types->has($code)) {
                $ids[] = $types->get($code)->id;
            }
        }

        return array_values(array_unique($ids));
    }

    /**
     * Map WordPress service term IDs to Service IDs.
     *
     * @param  array<int>  $wpTermIds
     * @return array<int> Core service IDs
     */
    public function mapServices(array $wpTermIds): array
    {
        if (empty($wpTermIds)) {
            return [];
        }

        $services = $this->getCachedDictionary('services', fn () => Service::all()->keyBy('code'));

        $ids = [];
        foreach ($wpTermIds as $wpTermId) {
            $code = (string) $wpTermId;
            if ($services->has($code)) {
                $ids[] = $services->get($code)->id;
            }
        }

        return array_values(array_unique($ids));
    }

    /**
     * Map WordPress service term IDs to SpecialistProfile IDs (codes that are specialist profiles).
     *
     * @param  array<int>  $wpTermIds
     * @return array<int> Core specialist_profile IDs
     */
    public function mapSpecialistProfiles(array $wpTermIds): array
    {
        if (empty($wpTermIds)) {
            return [];
        }

        $profiles = $this->getCachedDictionary('specialist_profiles', fn () => SpecialistProfile::all()->keyBy('code'));

        $ids = [];
        foreach ($wpTermIds as $wpTermId) {
            $code = (string) $wpTermId;
            if ($profiles->has($code)) {
                $ids[] = $profiles->get($code)->id;
            }
        }

        return array_values(array_unique($ids));
    }

    /**
     * Route hp_listing_service term IDs to organization_type, specialist_profile, and service IDs.
     * Each WP term is looked up by code in the three dictionaries.
     *
     * @param  array<int>  $wpServiceTermIds
     * @return array{organization_type_ids: array<int>, specialist_profile_ids: array<int>, service_ids: array<int>}
     */
    public function routeServiceTerms(array $wpServiceTermIds): array
    {
        $orgTypeIds = $this->mapOrganizationTypes($wpServiceTermIds);
        $specialistIds = $this->mapSpecialistProfiles($wpServiceTermIds);
        $serviceIds = $this->mapServices($wpServiceTermIds);

        return [
            'organization_type_ids' => $orgTypeIds,
            'specialist_profile_ids' => $specialistIds,
            'service_ids' => $serviceIds,
        ];
    }

    /**
     * Map WordPress ownership term ID to OwnershipType ID.
     *
     * @param  array<int>  $wpTermIds
     */
    public function mapOwnershipType(array $wpTermIds): ?int
    {
        if (empty($wpTermIds)) {
            return null;
        }

        $ownershipTypes = $this->getCachedDictionary('ownership_types', fn () => OwnershipType::all()->keyBy('code'));

        foreach ($wpTermIds as $wpTermId) {
            $code = (string) $wpTermId;
            if ($ownershipTypes->has($code)) {
                return $ownershipTypes->get($code)->id;
            }
        }

        return null;
    }

    /**
     * @param  callable(): Collection<string, \Illuminate\Database\Eloquent\Model>  $loader
     * @return Collection<string, \Illuminate\Database\Eloquent\Model>
     */
    private function getCachedDictionary(string $key, callable $loader): Collection
    {
        if (! isset($this->cache[$key])) {
            $this->cache[$key] = $loader();
        }

        return $this->cache[$key];
    }
}
