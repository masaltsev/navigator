<?php

namespace Database\Factories;

use App\Models\EventInstance;
use Illuminate\Database\Eloquent\Factories\Factory;

/**
 * @extends \Illuminate\Database\Eloquent\Factories\Factory<\App\Models\EventInstance>
 */
class EventInstanceFactory extends Factory
{
    protected $model = EventInstance::class;

    /**
     * Define the model's default state.
     *
     * @return array<string, mixed>
     */
    public function definition(): array
    {
        return [
            'id' => $this->faker->uuid(),
            'start_datetime' => now()->addDay(),
            'end_datetime' => now()->addDay()->addHours(2),
            'status' => 'scheduled',
        ];
    }

    /**
     * Indicate that the instance is scheduled.
     */
    public function scheduled(): static
    {
        return $this->state(function (array $attributes) {
            return [
                'status' => 'scheduled',
            ];
        });
    }
}
