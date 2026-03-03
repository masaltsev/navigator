<?php

namespace Database\Seeders;

use App\Models\User;
use Illuminate\Database\Console\Seeds\WithoutModelEvents;
use Illuminate\Database\Seeder;

class DatabaseSeeder extends Seeder
{
    use WithoutModelEvents;

    /**
     * Seed the application's database.
     */
    public function run(): void
    {
        // Seed dictionaries (new names from dictionaries_refactoring.md)
        $this->call([
            ThematicCategorySeeder::class,
            ServiceSeeder::class,
            OrganizationTypeSeeder::class,
            OwnershipTypeSeeder::class,
            SpecialistProfileSeeder::class,
        ]);

        // User::factory(10)->create();

        User::factory()->create([
            'name' => 'Test User',
            'email' => 'test@example.com',
        ]);
    }
}
