<?php

namespace Database\Factories;

use App\Models\OwnershipType;
use Illuminate\Database\Eloquent\Factories\Factory;

/**
 * @extends \Illuminate\Database\Eloquent\Factories\Factory<\App\Models\OwnershipType>
 */
class OwnershipTypeFactory extends Factory
{
    protected $model = OwnershipType::class;

    /**
     * Define the model's default state.
     *
     * @return array<string, mixed>
     */
    public function definition(): array
    {
        return [
            'name' => $this->faker->words(3, true),
            'code' => $this->faker->lexify('own_???'),
        ];
    }
}
