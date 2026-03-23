<?php

namespace Database\Factories;

use App\Models\Event;
use App\Models\Organizer;
use Illuminate\Database\Eloquent\Factories\Factory;

/**
 * @extends \Illuminate\Database\Eloquent\Factories\Factory<\App\Models\Event>
 */
class EventFactory extends Factory
{
    protected $model = Event::class;

    /**
     * Define the model's default state.
     *
     * @return array<string, mixed>
     */
    public function definition(): array
    {
        return [
            'id' => $this->faker->uuid(),
            'title' => $this->faker->sentence(),
            'description' => $this->faker->paragraph(),
            'attendance_mode' => 'offline',
            'status' => 'approved',
            'organizer_id' => Organizer::factory(),
        ];
    }

    /**
     * Indicate that the event is approved.
     */
    public function approved(): static
    {
        return $this->state(function (array $attributes) {
            return [
                'status' => 'approved',
            ];
        });
    }
}
