<?php

namespace App\Http\Resources\Api\V1;

use Illuminate\Http\Request;
use Illuminate\Http\Resources\Json\JsonResource;

class ArticleResource extends JsonResource
{
    /**
     * Transform the resource into an array.
     *
     * @return array<string, mixed>
     */
    public function toArray(Request $request): array
    {
        // List view (for index)
        if ($request->routeIs('*.index')) {
            return [
                'id' => $this->id,
                'title' => $this->title,
                'slug' => $this->slug,
                'excerpt' => $this->excerpt,
                'featured_image_url' => $this->featured_image_url,
                'published_at' => $this->published_at?->toIso8601String(),
                'related_thematic_category' => $this->relatedThematicCategory ? [
                    'id' => $this->relatedThematicCategory->id,
                    'name' => $this->relatedThematicCategory->name,
                ] : null,
                'organization' => $this->organization ? [
                    'id' => $this->organization->id,
                    'title' => $this->organization->title,
                ] : null,
            ];
        }

        // Detail view (for show)
        return [
            'id' => $this->id,
            'title' => $this->title,
            'slug' => $this->slug,
            'excerpt' => $this->excerpt,
            'content' => $this->content,
            'content_url' => $this->content_url,
            'featured_image_url' => $this->featured_image_url,
            'published_at' => $this->published_at?->toIso8601String(),
            'related_thematic_category' => $this->relatedThematicCategory ? [
                'id' => $this->relatedThematicCategory->id,
                'name' => $this->relatedThematicCategory->name,
            ] : null,
            'organization' => $this->organization ? [
                'id' => $this->organization->id,
                'title' => $this->organization->title,
            ] : null,
        ];
    }
}
