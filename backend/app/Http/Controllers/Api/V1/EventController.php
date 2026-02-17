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
     * - lat, lng, radius_km: geo-radius filter (for offline/mixed events)
     */
    public function index(Request $request): AnonymousResourceCollection
    {
        $query = EventInstance::query()
            ->where('status', 'scheduled')
            ->with([
                'event' => function ($q) {
                    $q->where('status', 'approved')
                        ->with(['organizer.organizable', 'categories', 'venues']);
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
