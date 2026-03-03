<?php

namespace App\Http\Controllers\Api\V1;

use App\Http\Controllers\Controller;
use App\Http\Resources\Api\V1\EventResource;
use App\Models\EventInstance;
use Carbon\Carbon;
use Illuminate\Http\Request;
use Illuminate\Http\Resources\Json\AnonymousResourceCollection;

class EventController extends Controller
{
    /**
     * Display a listing of scheduled event instances.
     *
     * Filters:
     * - time_frame: today, tomorrow, this_week, this_month
     * - attendance_mode: offline, online, mixed
     * - city_fias_id or city_fias_id[]: filter by city (level 4); matches venue.city_fias_id, fallback to venue.fias_id when city_fias_id empty
     * - regioniso: filter by region ISO code (e.g., RU-MOW)
     * - region_code: filter by region code for new regions without ISO (LNR, DNR, Kherson, Zaporozhye)
     * - lat, lng, radius_km: geo-radius filter (for offline/mixed events)
     */
    public function index(Request $request): AnonymousResourceCollection
    {
        $query = EventInstance::query()
            ->where('status', 'scheduled')
            ->with([
                'event' => function ($q) {
                    $q->where('status', 'approved')
                        ->with([
                            'organizer.organizable',
                            'categories',
                            'venues' => function ($q2) {
                                $q2->select(
                                    'venues.id',
                                    'venues.address_raw',
                                    'venues.coordinates',
                                    'venues.fias_id',
                                    'venues.city_fias_id',
                                    'venues.region_iso',
                                    'venues.region_code'
                                );
                            },
                        ]);
                },
            ])
            ->whereHas('event', function ($q) {
                $q->where('status', 'approved');
            });

        // Time frame filter
        if ($request->filled('time_frame')) {
            $timeFrame = $request->input('time_frame');
            $now = Carbon::now();

            match ($timeFrame) {
                'today' => $query->whereDate('start_datetime', $now->toDateString()),
                'tomorrow' => $query->whereDate('start_datetime', $now->copy()->addDay()->toDateString()),
                'this_week' => $query->whereBetween('start_datetime', [
                    $now->startOfWeek(),
                    $now->copy()->endOfWeek(),
                ]),
                'this_month' => $query->whereBetween('start_datetime', [
                    $now->startOfMonth(),
                    $now->copy()->endOfMonth(),
                ]),
                default => null,
            };
        } else {
            // Default: future events
            $query->where('start_datetime', '>=', Carbon::now());
        }

        // Attendance mode filter
        if ($request->filled('attendance_mode')) {
            $query->whereHas('event', function ($q) use ($request) {
                $q->where('attendance_mode', $request->input('attendance_mode'));
            });
        }

        // Filter events by city_fias_id (via event venues)
        $cityFiasIds = $request->filled('city_fias_id')
            ? (array) $request->input('city_fias_id')
            : [];

        if ($cityFiasIds !== []) {
            $cityFiasIds = array_filter(array_map('strval', $cityFiasIds));

            if ($cityFiasIds !== []) {
                $query->whereHas('event.venues', function ($q) use ($cityFiasIds) {
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

        // Filter events by region (ISO or region_code)
        if ($request->filled('regioniso') || $request->filled('region_code')) {
            $regionIso = $request->input('regioniso');
            $regionCode = $request->input('region_code');

            $query->whereHas('event.venues', function ($q) use ($regionIso, $regionCode) {
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

        // Geo-radius filter (only for offline/mixed events)
        if ($request->filled(['lat', 'lng', 'radius_km'])) {
            $lat = $request->input('lat');
            $lng = $request->input('lng');
            $radiusKm = $request->input('radius_km');
            $radiusMeters = $radiusKm * 1000;

            $query->whereHas('event.venues', function ($q) use ($lat, $lng, $radiusMeters) {
                $q->whereRaw(
                    'ST_DWithin(coordinates, ST_MakePoint(?, ?)::geography, ?)',
                    [$lng, $lat, $radiusMeters]
                );
            })->whereHas('event', function ($q) {
                $q->whereIn('attendance_mode', ['offline', 'mixed']);
            });
        }

        $events = $query->orderBy('start_datetime')->paginate($request->input('per_page', 15));

        return EventResource::collection($events);
    }
}
