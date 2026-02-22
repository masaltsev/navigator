<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

return new class extends Migration
{
    /**
     * Run the migrations.
     * Backfill: for settlements (fias_level=6) without city_fias_id, set city_fias_id = fias_id.
     * This allows filtering by settlement when city is not available from DaData.
     */
    public function up(): void
    {
        DB::table('venues')
            ->where('fias_level', '6')
            ->where(function ($query) {
                $query->whereNull('city_fias_id')->orWhere('city_fias_id', '');
            })
            ->whereNotNull('fias_id')
            ->where('fias_id', '!=', '')
            ->update(['city_fias_id' => DB::raw('fias_id')]);
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        // No rollback needed - this is a data fix, not a schema change
    }
};
