<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

return new class extends Migration
{
    /**
     * Run the migrations.
     * Backfill: for federal cities (Moscow, Saint Petersburg, Sevastopol) with fias_level=1,
     * set city_fias_id = fias_id so the city filter works correctly.
     */
    public function up(): void
    {
        DB::table('venues')
            ->where('fias_level', '1')
            ->whereIn('region_iso', ['RU-MOW', 'RU-SPE', 'RU-SEV'])
            ->where(function ($query) {
                $query->whereNull('city_fias_id')->orWhere('city_fias_id', '');
            })
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
