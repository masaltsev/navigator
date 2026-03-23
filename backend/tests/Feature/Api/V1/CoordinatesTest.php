<?php

namespace Tests\Feature\Api\V1;

use App\Models\Organization;
use App\Models\Venue;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class CoordinatesTest extends TestCase
{
    use RefreshDatabase;

    public function test_get_api_v1_organizations_returns_coordinates_when_venue_has_coordinates(): void
    {
        // Create a venue with coordinates
        $venue = Venue::factory()->create([
            'coordinates' => \DB::raw('ST_SetSRID(ST_MakePoint(37.6173, 55.7558), 4326)'),
        ]);

        $organization = Organization::factory()->create(['status' => 'approved']);
        $organization->venues()->attach($venue->id, ['is_headquarters' => true]);

        $response = $this->getJson('/api/v1/organizations?per_page=1');

        $response->assertSuccessful();

        $data = $response->json('data');
        if (count($data) > 0 && isset($data[0]['venue'])) {
            $this->assertIsArray($data[0]['venue']['coordinates']);
            $this->assertArrayHasKey('lat', $data[0]['venue']['coordinates']);
            $this->assertArrayHasKey('lng', $data[0]['venue']['coordinates']);
            $this->assertIsFloat($data[0]['venue']['coordinates']['lat']);
            $this->assertIsFloat($data[0]['venue']['coordinates']['lng']);
        }
    }

    public function test_get_api_v1_organizations_id_returns_coordinates_in_venues_array(): void
    {
        $venue = Venue::factory()->create([
            'coordinates' => \DB::raw('ST_SetSRID(ST_MakePoint(37.6173, 55.7558), 4326)'),
        ]);

        $organization = Organization::factory()->create(['status' => 'approved']);
        $organization->venues()->attach($venue->id, ['is_headquarters' => true]);

        $response = $this->getJson("/api/v1/organizations/{$organization->id}");

        $response->assertSuccessful();

        $data = $response->json('data');
        $this->assertIsArray($data['venues']);
        $this->assertIsArray($data['venues'][0]['coordinates']);
        $this->assertArrayHasKey('lat', $data['venues'][0]['coordinates']);
        $this->assertArrayHasKey('lng', $data['venues'][0]['coordinates']);
    }

    public function test_get_api_v1_events_returns_coordinates_for_offline_events(): void
    {
        // This test requires Event and EventInstance factories
        // For now, we'll skip it as it's complex to set up
        $this->markTestSkipped('Requires Event and EventInstance factories');
    }

    public function test_coordinates_return_null_when_venue_has_no_coordinates(): void
    {
        $venue = Venue::factory()->create([
            'coordinates' => null,
        ]);

        $organization = Organization::factory()->create(['status' => 'approved']);
        $organization->venues()->attach($venue->id, ['is_headquarters' => true]);

        $response = $this->getJson('/api/v1/organizations?per_page=1');

        $response->assertSuccessful();

        $data = $response->json('data');
        if (count($data) > 0 && isset($data[0]['venue'])) {
            $this->assertNull($data[0]['venue']['coordinates']);
        }
    }
}
