<?php

namespace App\Http\Controllers\Api\V1;

use App\Http\Controllers\Controller;
use App\Http\Resources\Api\V1\OrganizationResource;
use App\Models\Organization;
use Illuminate\Http\Request;
use Illuminate\Http\Resources\Json\AnonymousResourceCollection;

class OrganizationController extends Controller
{
    /**
     * Display a listing of approved organizations.
     *
     * Filters:
     * - city_fias_id: filter by city FIAS ID
     * - problem_category_id[]: filter by problem categories
     * - service_id[]: filter by services
     * - lat, lng, radius_km: geo-radius filter
     * - works_with_elderly: filter by works_with_elderly flag (default: true)
     * - status: filter by status (default: approved)
     */
    public function index(Request $request): AnonymousResourceCollection
    {
        $query = Organization::query()
            ->where('status', 'approved')
            ->with([
                'organizationType',
                'coverageLevel',
                'problemCategories:id,name',
                'services:id,name',
                'venues' => function ($q) {
                    $q->select('venues.id', 'venues.address_raw', 'venues.coordinates', 'venues.fias_id')
                        ->orderBy('organization_venues.is_headquarters', 'desc')
                        ->limit(1);
                },
            ]);

        // Filter by works_with_elderly (default: true)
        if ($request->has('works_with_elderly')) {
            $query->where('works_with_elderly', $request->boolean('works_with_elderly'));
        } else {
            $query->where('works_with_elderly', true);
        }

        // Filter by city_fias_id (via venues)
        if ($request->filled('city_fias_id')) {
            $query->whereHas('venues', function ($q) use ($request) {
                $q->where('fias_id', 'LIKE', $request->input('city_fias_id').'%');
            });
        }

        // Filter by problem categories
        if ($request->filled('problem_category_id')) {
            $categoryIds = is_array($request->input('problem_category_id'))
                ? $request->input('problem_category_id')
                : [$request->input('problem_category_id')];
            $query->whereHas('problemCategories', function ($q) use ($categoryIds) {
                $q->whereIn('problem_categories.id', $categoryIds);
            });
        }

        // Filter by services
        if ($request->filled('service_id')) {
            $serviceIds = is_array($request->input('service_id'))
                ? $request->input('service_id')
                : [$request->input('service_id')];
            $query->whereHas('services', function ($q) use ($serviceIds) {
                $q->whereIn('services.id', $serviceIds);
            });
        }

        // Geo-radius filter (lat, lng, radius_km)
        if ($request->filled(['lat', 'lng', 'radius_km'])) {
            $lat = $request->input('lat');
            $lng = $request->input('lng');
            $radiusKm = $request->input('radius_km');
            $radiusMeters = $radiusKm * 1000;

            $query->whereHas('venues', function ($q) use ($lat, $lng, $radiusMeters) {
                $q->whereRaw(
                    'ST_DWithin(coordinates, ST_MakePoint(?, ?)::geography, ?)',
                    [$lng, $lat, $radiusMeters]
                );
            });
        }

        $organizations = $query->paginate($request->input('per_page', 15));

        return OrganizationResource::collection($organizations);
    }

    /**
     * Display the specified organization with full details.
     */
    public function show(string $id): OrganizationResource
    {
        $organization = Organization::query()
            ->where('status', 'approved')
            ->with([
                'organizationType',
                'ownershipType',
                'coverageLevel',
                'problemCategories',
                'services',
                'venues',
                'events' => function ($q) {
                    $q->where('status', 'approved')
                        ->with(['categories', 'venues'])
                        ->orderBy('created_at', 'desc')
                        ->limit(10);
                },
                'articles' => function ($q) {
                    $q->where('status', 'published')
                        ->orderBy('published_at', 'desc')
                        ->limit(5);
                },
            ])
            ->findOrFail($id);

        return new OrganizationResource($organization);
    }
}
