<?php

namespace Database\Factories;

use App\Models\Article;
use Illuminate\Database\Eloquent\Factories\Factory;

/**
 * @extends \Illuminate\Database\Eloquent\Factories\Factory<\App\Models\Article>
 */
class ArticleFactory extends Factory
{
    protected $model = Article::class;

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
            'slug' => $this->faker->slug(),
            'excerpt' => $this->faker->paragraph(),
            'content' => $this->faker->paragraphs(3, true),
            'status' => 'published',
            'published_at' => now(),
        ];
    }

    /**
     * Indicate that the article is published.
     */
    public function published(): static
    {
        return $this->state(function (array $attributes) {
            return [
                'status' => 'published',
                'published_at' => now(),
            ];
        });
    }

    /**
     * Indicate that the article is draft.
     */
    public function draft(): static
    {
        return $this->state(function (array $attributes) {
            return [
                'status' => 'draft',
                'published_at' => null,
            ];
        });
    }

    /**
     * Indicate that the article has a thematic category.
     */
    public function withThematicCategory($categoryId): static
    {
        return $this->state(function (array $attributes) use ($categoryId) {
            return [
                'related_thematic_category_id' => $categoryId,
            ];
        });
    }

    /**
     * Indicate that the article has a service.
     */
    public function withService($serviceId): static
    {
        return $this->state(function (array $attributes) use ($serviceId) {
            return [
                'related_service_id' => $serviceId,
            ];
        });
    }

    /**
     * Indicate that the article has an organization.
     */
    public function withOrganization($organizationId): static
    {
        return $this->state(function (array $attributes) use ($organizationId) {
            return [
                'organization_id' => $organizationId,
            ];
        });
    }
}
