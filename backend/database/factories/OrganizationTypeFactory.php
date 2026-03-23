<?php

namespace Database\Factories;

use App\Models\OrganizationType;
use Illuminate\Database\Eloquent\Factories\Factory;

/**
 * @extends \Illuminate\Database\Eloquent\Factories\Factory<\App\Models\OrganizationType>
 */
class OrganizationTypeFactory extends Factory
{
    protected $model = OrganizationType::class;

    /**
     * Define the model's default state.
     *
     * @return array<string, mixed>
     */
    public function definition(): array
    {
        return [
            'name' => $this->faker->words(3, true),
            'code' => $this->faker->lexify('type_???'),
        ];
    }
}
