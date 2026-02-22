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
        // Build region mapping: prefix -> region_code from venues with fias_level = 1
        $regionMap = [];
        $regions = DB::table('venues')
            ->whereNull('region_iso')
            ->whereNotNull('region_code')
            ->where('fias_level', '1')
            ->select('address_raw', 'region_code')
            ->get();

        foreach ($regions as $region) {
            // Extract region prefix from address (e.g., "Респ Луганская Народная" or "Херсонская обл")
            $prefix = null;
            if (preg_match('/^(Респ\s+[^,]+)/u', $region->address_raw, $matches)) {
                $prefix = $matches[1];
            } elseif (preg_match('/^([^,]+(?:Народн|обл|область))/u', $region->address_raw, $matches)) {
                $prefix = $matches[1];
            } elseif (preg_match('/^(Россия,\s*[^,]+)/u', $region->address_raw, $matches)) {
                $prefix = $matches[1];
            }

            if ($prefix !== null && ! isset($regionMap[$prefix])) {
                $regionMap[$prefix] = $region->region_code;
            }
        }

        // Update venues with fias_level = 4 or 6 that match region prefixes
        foreach ($regionMap as $prefix => $regionCode) {
            $prefixPattern = $prefix.'%';
            DB::table('venues')
                ->whereNull('region_iso')
                ->where(function ($q) {
                    $q->whereNull('region_code')->orWhere('region_code', '');
                })
                ->whereIn('fias_level', ['4', '6'])
                ->where('address_raw', 'LIKE', $prefixPattern)
                ->update(['region_code' => $regionCode]);
        }
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        // Clear region_code for venues that were backfilled (fias_level = 4 or 6, region_iso = null)
        DB::table('venues')
            ->whereNull('region_iso')
            ->whereIn('fias_level', ['4', '6'])
            ->whereNotNull('region_code')
            ->update(['region_code' => null]);
    }
};
