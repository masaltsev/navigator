<?php

namespace App\Http\Resources\Api\V1;

use Illuminate\Http\Request;
use Illuminate\Http\Resources\Json\JsonResource;

class OrganizationResource extends JsonResource
{
    /**
     * Transform the resource into an array.
     *
     * @return array<string, mixed>
     */
    public function toArray(Request $request): array
    {
        $primaryPhone = $this->organizer?->contact_phones[0] ?? null;
        $isListView = $request->route()?->getActionMethod() === 'index';

        if ($isListView) {
            return [
                'id' => $this->id,
                'type' => 'Organization',
                'title' => $this->title,
                'description' => $this->description ? mb_substr($this->description, 0, 150).'...' : null,
                'primary_phone' => $primaryPhone,
                'organization_types' => $this->organizationTypes->map(fn ($t) => ['id' => $t->id, 'name' => $t->name]),
                'coverage_level' => $this->coverageLevel?->name,
                'venue' => $this->when(
                    $this->venues->isNotEmpty(),
                    function () {
                        $venue = $this->venues->first();

                        return [
                            'id' => $venue->id,
                            'address' => $venue->address_raw,
                            'coordinates' => $venue->coordinates_array,
                        ];
                    }
                ),
                'thematic_categories' => $this->thematicCategories->map(fn ($cat) => [
                    'id' => $cat->id,
                    'name' => $cat->name,
                ]),
                'specialist_profiles' => $this->specialistProfiles->map(fn ($p) => ['id' => $p->id, 'name' => $p->name]),
                'services' => $this->services->take(3)->map(fn ($svc) => [
                    'id' => $svc->id,
                    'name' => $svc->name,
                ]),
            ];
        }

        return [
            'id' => $this->id,
            'type' => 'Organization',
            'title' => $this->title,
            'description' => $this->description,
            'primary_phone' => $primaryPhone,
            'organization_types' => $this->organizationTypes->map(fn ($t) => ['id' => $t->id, 'name' => $t->name]),
            'ownership_type' => [
                'id' => $this->ownershipType?->id,
                'name' => $this->ownershipType?->name,
            ],
            'coverage_level' => [
                'id' => $this->coverageLevel?->id,
                'name' => $this->coverageLevel?->name,
            ],
            'inn' => $this->inn,
            'ogrn' => $this->ogrn,
            'site_urls' => $this->site_urls,
            'venues' => $this->venues->map(function ($venue) {
                return [
                    'id' => $venue->id,
                    'address' => $venue->address_raw,
                    'fias_id' => $venue->fias_id,
                    'coordinates' => $venue->coordinates_array,
                    'is_headquarters' => $venue->pivot->is_headquarters ?? false,
                ];
            }),
            'thematic_categories' => $this->thematicCategories->map(fn ($cat) => [
                'id' => $cat->id,
                'name' => $cat->name,
            ]),
            'specialist_profiles' => $this->specialistProfiles->map(fn ($p) => ['id' => $p->id, 'name' => $p->name]),
            'services' => $this->services->map(fn ($svc) => [
                'id' => $svc->id,
                'name' => $svc->name,
            ]),
            'events' => $this->when(
                $this->relationLoaded('events'),
                fn () => $this->events->map(fn ($event) => [
                    'id' => $event->id,
                    'title' => $event->title,
                    'attendance_mode' => $event->attendance_mode,
                    'start_datetime' => $event->instances->first()?->start_datetime?->toIso8601String(),
                ])
            ),
            'articles' => $this->when(
                $this->relationLoaded('articles'),
                fn () => $this->articles->map(fn ($article) => [
                    'id' => $article->id,
                    'title' => $article->title,
                    'slug' => $article->slug,
                    'excerpt' => $article->excerpt,
                ])
            ),
        ];
    }
}
