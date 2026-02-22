<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

return new class extends Migration
{
    /**
     * Run the migrations.
     * Backfill: for regions (fias_level=1) that are not federal cities, set city_fias_id = fias_id.
     * Federal cities (RU-MOW, RU-SPE, RU-SEV) are already handled by previous migration.
     */
    public function up(): void
    {
        DB::table('venues')
            ->where('fias_level', '1')
            ->whereNotIn('region_iso', ['RU-MOW', 'RU-SPE', 'RU-SEV'])
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
