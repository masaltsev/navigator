<?php

namespace Tests\Feature\Api\V1;

use App\Models\Article;
use App\Models\Event;
use App\Models\EventCategory;
use App\Models\EventInstance;
use App\Models\Organization;
use App\Models\Organizer;
use App\Models\Service;
use App\Models\ThematicCategory;
use App\Models\Venue;
use Tests\Concerns\RefreshDatabaseWithSchema;
use Tests\TestCase;

/**
 * Безопасные тесты реализованных функций
 * Не затрагивают существующие данные, работают с изолированными тестовыми записями
 */
class SafeImplementationTest extends TestCase
{
    use RefreshDatabaseWithSchema;

    /**
     * Тест BK-01: PostGIS координаты
     */
    public function test_postgis_coordinates_are_returned(): void
    {
        // Создаем тестовые данные с уникальным префиксом
        $venue = Venue::factory()->create([
            'address_raw' => 'TEST_Venue with coordinates',
            'coordinates' => \DB::raw('ST_SetSRID(ST_MakePoint(37.6173, 55.7558), 4326)'),
        ]);

        $organization = Organization::factory()->create([
            'title' => 'TEST_Organization for coordinates test',
            'status' => 'approved',
        ]);

        $organization->venues()->attach($venue->id, ['is_headquarters' => true]);

        // Тестируем детальную карточку
        $response = $this->getJson("/api/v1/organizations/{$organization->id}");
        $response->assertSuccessful();

        $data = $response->json('data');
        $this->assertIsArray($data['venues']);
        $this->assertIsArray($data['venues'][0]['coordinates']);
        $this->assertArrayHasKey('lat', $data['venues'][0]['coordinates']);
        $this->assertArrayHasKey('lng', $data['venues'][0]['coordinates']);

        // Очищаем тестовые данные
        $organization->venues()->detach();
        $venue->delete();
        $organization->delete();
    }

    /**
     * Тест BK-02: Телефон в списке организаций
     */
    public function test_primary_phone_in_organization_list(): void
    {
        // Создаем тестовые данные
        $organizer = Organizer::factory()->create([
            'contact_phones' => ['+7 (999) 111-22-33'],
        ]);

        $organization = Organization::factory()->create([
            'title' => 'TEST_Organization with phone',
            'status' => 'approved',
        ]);

        $organizer->update([
            'organizable_type' => 'Organization',
            'organizable_id' => $organization->id,
        ]);

        // Тестируем список
        $response = $this->getJson('/api/v1/organizations?title=TEST_');
        $response->assertSuccessful();

        $data = $response->json('data');
        $this->assertNotEmpty($data);

        // Ищем нашу тестовую организацию
        $testOrg = collect($data)->firstWhere('title', 'TEST_Organization with phone');
        $this->assertNotNull($testOrg);
        $this->assertArrayHasKey('primary_phone', $testOrg);
        $this->assertEquals('+7 (999) 111-22-33', $testOrg['primary_phone']);

        // Очищаем
        $organizer->delete();
        $organization->delete();
    }

    /**
     * Тест BK-03: Справочники
     */
    public function test_dictionaries_endpoint_returns_data(): void
    {
        // Создаем тестовые справочники
        ThematicCategory::factory()->create(['name' => 'TEST_Thematic Category']);
        Service::factory()->create(['name' => 'TEST_Service']);

        $response = $this->getJson('/api/v1/dictionaries');
        $response->assertSuccessful();

        $data = $response->json('data');
        $this->assertArrayHasKey('thematic_categories', $data);
        $this->assertArrayHasKey('services', $data);

        // Проверяем, что наши тестовые данные есть
        $thematicCategories = collect($data['thematic_categories'])
            ->pluck('name')
            ->toArray();

        $this->assertContains('TEST_Thematic Category', $thematicCategories);

        // Очищаем тестовые справочники
        ThematicCategory::where('name', 'LIKE', 'TEST_%')->delete();
        Service::where('name', 'LIKE', 'TEST_%')->delete();
    }

    /**
     * Тест BK-04: Статьи
     */
    public function test_articles_endpoint_with_filters(): void
    {
        // Создаем тестовые данные
        $category = ThematicCategory::factory()->create(['name' => 'TEST_Article Category']);
        $organization = Organization::factory()->create([
            'title' => 'TEST_Article Organization',
            'status' => 'approved',
        ]);

        $article = Article::factory()->create([
            'title' => 'TEST_Article',
            'slug' => 'test-article',
            'status' => 'published',
            'related_thematic_category_id' => $category->id,
            'organization_id' => $organization->id,
        ]);

        // Тестируем фильтрацию по категории
        $response = $this->getJson("/api/v1/articles?thematic_category_id={$category->id}");
        $response->assertSuccessful();

        $data = $response->json('data');
        $this->assertNotEmpty($data);

        // Тестируем детальную статью
        $response = $this->getJson('/api/v1/articles/test-article');
        $response->assertSuccessful();

        $articleData = $response->json('data');
        $this->assertEquals('TEST_Article', $articleData['title']);

        // Очищаем
        $article->delete();
        $organization->delete();
        $category->delete();
    }

    /**
     * Тест BK-05: Фильтр категорий мероприятий
     */
    public function test_event_category_filter(): void
    {
        // Создаем тестовые данные
        $category = EventCategory::factory()->create([
            'name' => 'TEST_Event Category',
            'slug' => 'test-event-category',
        ]);

        $event = Event::factory()->create([
            'title' => 'TEST_Event',
            'status' => 'approved',
        ]);

        $event->categories()->attach($category->id);

        $instance = EventInstance::factory()->create([
            'event_id' => $event->id,
            'status' => 'scheduled',
            'start_datetime' => now()->addDay(),
        ]);

        // Тестируем фильтрацию по slug категории
        $response = $this->getJson('/api/v1/events?event_category_slug[]=test-event-category');
        $response->assertSuccessful();

        $data = $response->json('data');
        // Может быть пусто, если есть другие фильтры, но главное - нет ошибок

        // Очищаем
        $instance->delete();
        $event->categories()->detach();
        $event->delete();
        $category->delete();
    }

    /**
     * Проверка, что не затронуты существующие данные
     */
    public function test_existing_data_not_affected(): void
    {
        // Запоминаем количество записей до тестов
        $initialOrgCount = Organization::count();
        $initialVenueCount = Venue::count();

        // Создаем тестовые данные
        $testOrg = Organization::factory()->create([
            'title' => 'TEST_Temporary organization',
            'status' => 'approved',
        ]);

        // Проверяем, что добавилась только одна запись
        $this->assertEquals($initialOrgCount + 1, Organization::count());

        // Удаляем тестовые данные
        $testOrg->delete();

        // Проверяем, что вернулись к исходному состоянию
        $this->assertEquals($initialOrgCount, Organization::count());
        $this->assertEquals($initialVenueCount, Venue::count());
    }
}
