<?php

use App\Models\Article;
use App\Models\Organization;
use App\Models\Service;
use App\Models\ThematicCategory;
use Tests\Concerns\RefreshDatabaseWithSchema;

uses(RefreshDatabaseWithSchema::class);

test('GET /api/v1/articles returns published articles', function () {
    Article::factory()->create([
        'status' => 'published',
        'title' => 'Published Article',
    ]);

    Article::factory()->create([
        'status' => 'draft',
        'title' => 'Draft Article',
    ]);

    $response = $this->getJson('/api/v1/articles');

    $response->assertSuccessful();

    $data = $response->json('data');
    expect($data)->toBeArray();

    // Should only return published articles
    $titles = collect($data)->pluck('title')->toArray();
    expect($titles)->toContain('Published Article');
    expect($titles)->not->toContain('Draft Article');
});

test('GET /api/v1/articles filters by thematic_category_id', function () {
    $category1 = ThematicCategory::factory()->create();
    $category2 = ThematicCategory::factory()->create();

    Article::factory()->create([
        'status' => 'published',
        'related_thematic_category_id' => $category1->id,
        'title' => 'Article in Category 1',
    ]);

    Article::factory()->create([
        'status' => 'published',
        'related_thematic_category_id' => $category2->id,
        'title' => 'Article in Category 2',
    ]);

    $response = $this->getJson("/api/v1/articles?thematic_category_id={$category1->id}");

    $response->assertSuccessful();

    $data = $response->json('data');
    $titles = collect($data)->pluck('title')->toArray();

    expect($titles)->toContain('Article in Category 1');
    expect($titles)->not->toContain('Article in Category 2');
});

test('GET /api/v1/articles filters by service_id', function () {
    $service1 = Service::factory()->create();
    $service2 = Service::factory()->create();

    Article::factory()->create([
        'status' => 'published',
        'related_service_id' => $service1->id,
        'title' => 'Article for Service 1',
    ]);

    Article::factory()->create([
        'status' => 'published',
        'related_service_id' => $service2->id,
        'title' => 'Article for Service 2',
    ]);

    $response = $this->getJson("/api/v1/articles?service_id={$service1->id}");

    $response->assertSuccessful();

    $data = $response->json('data');
    $titles = collect($data)->pluck('title')->toArray();

    expect($titles)->toContain('Article for Service 1');
    expect($titles)->not->toContain('Article for Service 2');
});

test('GET /api/v1/articles filters by organization_id', function () {
    $org1 = Organization::factory()->create(['status' => 'approved']);
    $org2 = Organization::factory()->create(['status' => 'approved']);

    Article::factory()->create([
        'status' => 'published',
        'organization_id' => $org1->id,
        'title' => 'Article by Org 1',
    ]);

    Article::factory()->create([
        'status' => 'published',
        'organization_id' => $org2->id,
        'title' => 'Article by Org 2',
    ]);

    $response = $this->getJson("/api/v1/articles?organization_id={$org1->id}");

    $response->assertSuccessful();

    $data = $response->json('data');
    $titles = collect($data)->pluck('title')->toArray();

    expect($titles)->toContain('Article by Org 1');
    expect($titles)->not->toContain('Article by Org 2');
});

test('GET /api/v1/articles/{slug} returns article detail', function () {
    $article = Article::factory()->create([
        'status' => 'published',
        'slug' => 'test-article',
        'title' => 'Test Article',
        'content' => 'Article content here',
    ]);

    $response = $this->getJson('/api/v1/articles/test-article');

    $response->assertSuccessful();

    $data = $response->json('data');
    expect($data['slug'])->toBe('test-article');
    expect($data['title'])->toBe('Test Article');
    expect($data['content'])->toBe('Article content here');
});

test('GET /api/v1/articles/{slug} returns 404 for non-existent slug', function () {
    $response = $this->getJson('/api/v1/articles/non-existent-article');

    $response->assertNotFound();
});

test('GET /api/v1/articles/{slug} returns 404 for draft article', function () {
    $article = Article::factory()->create([
        'status' => 'draft',
        'slug' => 'draft-article',
    ]);

    $response = $this->getJson('/api/v1/articles/draft-article');

    $response->assertNotFound();
});

test('GET /api/v1/articles includes related_thematic_category and organization in response', function () {
    $category = ThematicCategory::factory()->create();
    $organization = Organization::factory()->create(['status' => 'approved']);

    Article::factory()->create([
        'status' => 'published',
        'related_thematic_category_id' => $category->id,
        'organization_id' => $organization->id,
    ]);

    $response = $this->getJson('/api/v1/articles?per_page=1');

    $response->assertSuccessful();

    $data = $response->json('data');
    $article = collect($data)->firstWhere('organization.id', $organization->id);

    expect($article)->not->toBeNull();
    expect($article['related_thematic_category'])->toBeArray();
    expect($article['related_thematic_category']['id'])->toBe($category->id);
    expect($article['related_thematic_category']['name'])->toBe($category->name);

    expect($article['organization'])->toBeArray();
    expect($article['organization']['id'])->toBe($organization->id);
    expect($article['organization']['title'])->toBe($organization->title);
});

test('GET /api/v1/articles supports pagination', function () {
    Article::factory()->count(15)->create(['status' => 'published']);

    $response = $this->getJson('/api/v1/articles?per_page=5&page=2');

    $response->assertSuccessful();

    $data = $response->json('data');
    $meta = $response->json('meta');

    expect($data)->toHaveCount(5);
    expect($meta['per_page'])->toBe(5);
    expect($meta['current_page'])->toBe(2);
    expect($meta['total'])->toBe(15);
});
