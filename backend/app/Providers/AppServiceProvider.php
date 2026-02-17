<?php

namespace App\Providers;

use Illuminate\Database\Eloquent\Relations\Relation;
use Illuminate\Support\ServiceProvider;

class AppServiceProvider extends ServiceProvider
{
    /**
     * Register any application services.
     */
    public function register(): void
    {
        //
    }

    /**
     * Bootstrap any application services.
     */
    public function boot(): void
    {
        // Register morph map aliases for polymorphic relations (organizers)
        Relation::enforceMorphMap([
            'Organization' => \App\Models\Organization::class,
            'InitiativeGroup' => \App\Models\InitiativeGroup::class,
            'Individual' => \App\Models\Individual::class,
        ]);
    }
}
