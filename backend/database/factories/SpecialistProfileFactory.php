<?php

namespace Database\Factories;

use App\Models\SpecialistProfile;
use Illuminate\Database\Eloquent\Factories\Factory;

/**
 * @extends \Illuminate\Database\Eloquent\Factories\Factory<\App\Models\SpecialistProfile>
 */
class SpecialistProfileFactory extends Factory
{
    protected $model = SpecialistProfile::class;

    /**
     * Define the model's default state.
     *
     * @return array<string, mixed>
     */
    public function definition(): array
    {
        return [
            'name' => $this->faker->words(3, true),
            'code' => $this->faker->lexify('prof_???'),
        ];
    }
}
