<?php

namespace App\Http\Controllers\Api\V1;

use App\Http\Controllers\Controller;
use App\Models\EventCategory;
use App\Models\OrganizationType;
use App\Models\OwnershipType;
use App\Models\Service;
use App\Models\SpecialistProfile;
use App\Models\ThematicCategory;
use Illuminate\Http\JsonResponse;
use Illuminate\Support\Facades\Cache;

class DictionaryController extends Controller
{
    /**
     * Display all dictionaries in one request.
     *
     * Returns all active dictionaries needed for frontend:
     * - thematic_categories (with parent_id for hierarchy)
     * - services
     * - organization_types
     * - specialist_profiles
     * - ownership_types
     * - event_categories (with slug and icon_url)
     *
     * Cached for 1 hour to reduce database load.
     */
    public function index(): JsonResponse
    {
        return Cache::remember('v1_dictionaries', 3600, function () {
            return response()->json([
                'data' => [
                    'thematic_categories' => ThematicCategory::query()
                        ->select('id', 'name', 'code', 'parent_id')
                        ->orderBy('parent_id')
                        ->orderBy('name')
                        ->get(),
                    'services' => Service::query()
                        ->select('id', 'name', 'code', 'parent_id')
                        ->orderBy('name')
                        ->get(),
                    'organization_types' => OrganizationType::query()
                        ->select('id', 'name', 'code')
                        ->orderBy('name')
                        ->get(),
                    'specialist_profiles' => SpecialistProfile::query()
                        ->select('id', 'name', 'code')
                        ->orderBy('name')
                        ->get(),
                    'ownership_types' => OwnershipType::query()
                        ->select('id', 'name', 'code')
                        ->orderBy('name')
                        ->get(),
                    'event_categories' => EventCategory::query()
                        ->select('id', 'name', 'code', 'slug', 'icon_url')
                        ->orderBy('name')
                        ->get(),
                ],
            ]);
        });
    }
}
