<?php

namespace Database\Factories;

use App\Models\Organizer;
use Illuminate\Database\Eloquent\Factories\Factory;

/**
 * @extends \Illuminate\Database\Eloquent\Factories\Factory<\App\Models\Organizer>
 */
class OrganizerFactory extends Factory
{
    protected $model = Organizer::class;

    /**
     * Define the model's default state.
     *
     * @return array<string, mixed>
     */
    public function definition(): array
    {
        return [
            'id' => $this->faker->uuid(),
            'organizable_type' => 'Organization',
            'organizable_id' => function () {
                return \App\Models\Organization::factory()->create()->id;
            },
            'contact_phones' => [],
            'contact_emails' => [],
            'status' => 'approved',
        ];
    }

    /**
     * Indicate that the organizer has contact phones.
     */
    public function withPhones(?array $phones = null): static
    {
        return $this->state(function (array $attributes) use ($phones) {
            return [
                'contact_phones' => $phones ?? ['+7 (999) 123-45-67', '+7 (888) 987-65-43'],
            ];
        });
    }
}
