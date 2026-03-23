<?php

namespace App\Http\Controllers\Api\V1;

use App\Http\Controllers\Controller;
use App\Http\Resources\Api\V1\ArticleResource;
use App\Models\Article;
use Illuminate\Http\Request;
use Illuminate\Http\Resources\Json\AnonymousResourceCollection;

class ArticleController extends Controller
{
    /**
     * Display a listing of published articles.
     *
     * Filters:
     * - thematic_category_id: filter by related thematic category
     * - service_id: filter by related service
     * - organization_id: filter by organization
     * - page, per_page: pagination
     */
    public function index(Request $request): AnonymousResourceCollection
    {
        $query = Article::where('status', 'published')
            ->with(['relatedThematicCategory:id,name', 'organization:id,title'])
            ->orderBy('published_at', 'desc');

        // Filter by thematic category
        if ($request->filled('thematic_category_id')) {
            $query->where('related_thematic_category_id', $request->input('thematic_category_id'));
        }

        // Filter by service
        if ($request->filled('service_id')) {
            $query->where('related_service_id', $request->input('service_id'));
        }

        // Filter by organization
        if ($request->filled('organization_id')) {
            $query->where('organization_id', $request->input('organization_id'));
        }

        $articles = $query->paginate($request->input('per_page', 10));

        return ArticleResource::collection($articles);
    }

    /**
     * Display the specified article by slug.
     */
    public function show(string $slug): ArticleResource
    {
        $article = Article::where('status', 'published')
            ->where('slug', $slug)
            ->with(['relatedThematicCategory:id,name', 'organization:id,title'])
            ->firstOrFail();

        return new ArticleResource($article);
    }
}
