<?php

namespace Database\Factories;

use App\Models\Venue;
use Illuminate\Database\Eloquent\Factories\Factory;

/**
 * @extends \Illuminate\Database\Eloquent\Factories\Factory<\App\Models\Venue>
 */
class VenueFactory extends Factory
{
    protected $model = Venue::class;

    /**
     * Define the model's default state.
     *
     * @return array<string, mixed>
     */
    public function definition(): array
    {
        return [
            'id' => $this->faker->uuid(),
            'address_raw' => $this->faker->address(),
            'fias_id' => $this->faker->uuid(),
            'region_iso' => 'RU-MOW',
            'coordinates' => null,
        ];
    }

    /**
     * Indicate that the venue has coordinates.
     */
    public function withCoordinates(): static
    {
        return $this->state(function (array $attributes) {
            return [
                'coordinates' => \DB::raw('ST_SetSRID(ST_MakePoint(37.6173, 55.7558), 4326)'),
            ];
        });
    }
}
