<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

return new class extends Migration
{
    /**
     * Run the migrations.
     *
     * Update organizable_type from full class names to short morph map names.
     */
    public function up(): void
    {
        DB::table('organizers')
            ->where('organizable_type', 'App\Models\Organization')
            ->update(['organizable_type' => 'Organization']);

        DB::table('organizers')
            ->where('organizable_type', 'App\Models\InitiativeGroup')
            ->update(['organizable_type' => 'InitiativeGroup']);

        DB::table('organizers')
            ->where('organizable_type', 'App\Models\Individual')
            ->update(['organizable_type' => 'Individual']);
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        DB::table('organizers')
            ->where('organizable_type', 'Organization')
            ->update(['organizable_type' => 'App\Models\Organization']);

        DB::table('organizers')
            ->where('organizable_type', 'InitiativeGroup')
            ->update(['organizable_type' => 'App\Models\InitiativeGroup']);

        DB::table('organizers')
            ->where('organizable_type', 'Individual')
            ->update(['organizable_type' => 'App\Models\Individual']);
    }
};
