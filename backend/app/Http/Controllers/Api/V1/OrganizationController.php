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
     * - city_fias_id or city_fias_id[]: filter by city (level 4); matches venue.city_fias_id, fallback to venue.fias_id when city_fias_id empty
     * - regioniso: filter by region ISO code (e.g., RU-MOW)
     * - region_code: filter by region code for new regions without ISO (LNR, DNR, Kherson, Zaporozhye)
     * - thematic_category_id[]: filter by life situations (thematic categories)
     * - organization_type_id[]: filter by organization types (M:N)
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
                'organizationTypes:id,name',
                'coverageLevel',
                'thematicCategories:id,name',
                'specialistProfiles:id,name',
                'services:id,name',
                'venues' => function ($q) {
                    $q->select(
                        'venues.id',
                        'venues.address_raw',
                        'venues.coordinates',
                        'venues.fias_id',
                        'venues.city_fias_id',
                        'venues.region_iso',
                        'venues.region_code'
                    )
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

        // Filter by city_fias_id or city_fias_id[]: one id from client (e.g. "Вологда" → standardize → one id) returns all orgs in that city.
        // Uses venue.city_fias_id when set; fallback to venue.fias_id for legacy data.
        $cityFiasIds = $request->filled('city_fias_id')
            ? (array) $request->input('city_fias_id')
            : [];
        if ($cityFiasIds !== []) {
            $cityFiasIds = array_filter(array_map('strval', $cityFiasIds));
            if ($cityFiasIds !== []) {
                $query->whereHas('venues', function ($q) use ($cityFiasIds) {
                    $q->where(function ($q2) use ($cityFiasIds) {
                        $q2->whereIn('city_fias_id', $cityFiasIds)
                            ->orWhere(function ($q3) use ($cityFiasIds) {
                                $q3->whereNull('city_fias_id')
                                    ->where(function ($q4) use ($cityFiasIds) {
                                        foreach ($cityFiasIds as $id) {
                                            $q4->orWhere('fias_id', 'LIKE', $id.'%');
                                        }
                                    });
                            });
                    });
                });
            }
        }

        // Filter by region (ISO or region_code for new regions)
        if ($request->filled('regioniso') || $request->filled('region_code')) {
            $regionIso = $request->input('regioniso');
            $regionCode = $request->input('region_code');

            $query->whereHas('venues', function ($q) use ($regionIso, $regionCode) {
                $q->where(function ($q2) use ($regionIso, $regionCode) {
                    if ($regionIso !== null) {
                        $q2->orWhere('region_iso', $regionIso);
                    }

                    if ($regionCode !== null) {
                        $q2->orWhere('region_code', $regionCode);
                    }
                });
            });
        }

        // Filter by thematic categories (life situations)
        if ($request->filled('thematic_category_id')) {
            $categoryIds = is_array($request->input('thematic_category_id'))
                ? $request->input('thematic_category_id')
                : [$request->input('thematic_category_id')];
            $query->whereHas('thematicCategories', function ($q) use ($categoryIds) {
                $q->whereIn('thematic_categories.id', $categoryIds);
            });
        }

        // Filter by organization types (any of the given types)
        if ($request->filled('organization_type_id')) {
            $typeIds = is_array($request->input('organization_type_id'))
                ? $request->input('organization_type_id')
                : [$request->input('organization_type_id')];
            $query->whereHas('organizationTypes', function ($q) use ($typeIds) {
                $q->whereIn('organization_types.id', $typeIds);
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
                'organizationTypes',
                'ownershipType',
                'coverageLevel',
                'thematicCategories',
                'specialistProfiles',
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
