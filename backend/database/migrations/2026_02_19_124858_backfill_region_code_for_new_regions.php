<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

return new class extends Migration
{
    /**
     * Run the migrations.
     */
    public function up(): void
    {
        // For venues with region_iso = null (new regions: LNR, DNR, Kherson, Zaporozhye)
        // and fias_level = 1 (region level), use fias_id as region_code
        DB::table('venues')
            ->whereNull('region_iso')
            ->where('fias_level', '1')
            ->whereNotNull('fias_id')
            ->where('fias_id', '!=', '')
            ->where(function ($query) {
                $query->whereNull('region_code')->orWhere('region_code', '');
            })
            ->update(['region_code' => DB::raw('fias_id')]);
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        // Clear region_code for venues that were backfilled
        DB::table('venues')
            ->whereNull('region_iso')
            ->where('fias_level', '1')
            ->whereColumn('region_code', 'fias_id')
            ->update(['region_code' => null]);
    }
};
