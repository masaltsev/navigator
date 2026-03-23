<?php

namespace Database\Factories;

use App\Models\ThematicCategory;
use Illuminate\Database\Eloquent\Factories\Factory;

/**
 * @extends \Illuminate\Database\Eloquent\Factories\Factory<\App\Models\ThematicCategory>
 */
class ThematicCategoryFactory extends Factory
{
    protected $model = ThematicCategory::class;

    /**
     * Define the model's default state.
     *
     * @return array<string, mixed>
     */
    public function definition(): array
    {
        return [
            'name' => $this->faker->words(3, true),
            'code' => $this->faker->lexify('cat_???'),
            'parent_id' => null,
        ];
    }

    /**
     * Indicate that the category has a parent.
     */
    public function withParent(int $parentId): static
    {
        return $this->state(function (array $attributes) use ($parentId) {
            return [
                'parent_id' => $parentId,
            ];
        });
    }
}
