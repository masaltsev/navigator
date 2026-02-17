<?php

namespace App\Http\Resources\Api\V1;

use Illuminate\Http\Request;
use Illuminate\Http\Resources\Json\JsonResource;

class EventResource extends JsonResource
{
    /**
     * Transform the resource into an array.
     *
     * @return array<string, mixed>
     */
    public function toArray(Request $request): array
    {
        // EventResource wraps EventInstance, so we access the event via ->event
        $event = $this->event ?? null;

        if (! $event) {
            return [
                'id' => $this->id,
                'start_datetime' => $this->start_datetime?->toIso8601String(),
                'end_datetime' => $this->end_datetime?->toIso8601String(),
                'status' => $this->status,
            ];
        }

        // Compact list view (for index)
        return [
            'id' => $this->id,
            'event_id' => $event->id,
            'title' => $event->title,
            'description' => $event->description ? mb_substr($event->description, 0, 150).'...' : null,
            'attendance_mode' => $event->attendance_mode,
            'online_url' => $event->online_url,
            'start_datetime' => $this->start_datetime?->toIso8601String(),
            'end_datetime' => $this->end_datetime?->toIso8601String(),
            'status' => $this->status,
            'venue' => $this->when(
                $event->relationLoaded('venues') && $event->venues->isNotEmpty(),
                function () use ($event) {
                    $venue = $event->venues->first();

                    return [
                        'id' => $venue->id,
                        'address' => $venue->address_raw,
                        'coordinates' => $this->extractCoordinates($venue->coordinates),
                    ];
                }
            ),
            'categories' => $this->when(
                $event->relationLoaded('categories'),
                fn () => $event->categories->map(fn ($cat) => [
                    'id' => $cat->id,
                    'name' => $cat->name,
                    'slug' => $cat->slug,
                ])
            ),
            'organizer' => $this->when(
                $event->relationLoaded('organizer.organizable'),
                function () use ($event) {
                    $organizable = $event->organizer?->organizable;
                    if (! $organizable) {
                        return null;
                    }

                    return [
                        'id' => $organizable->id,
                        'type' => class_basename($organizable),
                        'name' => $organizable->title ?? $organizable->name ?? null,
                    ];
                }
            ),
        ];
    }

    /**
     * Extract coordinates from PostGIS geometry point.
     */
    private function extractCoordinates($coordinates): ?array
    {
        if (! $coordinates) {
            return null;
        }

        if (is_array($coordinates)) {
            return $coordinates;
        }

        // Placeholder for PostGIS extraction
        return null;
    }
}
