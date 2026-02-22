<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Run the migrations.
     * Backfill: venues with fias_level 4 or 6 get city_fias_id = fias_id; known Vologda microdistrict → city.
     */
    public function up(): void
    {
        Schema::table('venues', function (Blueprint $table) {
            $table->string('city_fias_id', 36)->nullable()->after('fias_level')->index();
        });

        DB::table('venues')->whereIn('fias_level', ['4', '6'])->update(['city_fias_id' => DB::raw('fias_id')]);

        $vologdaCityFiasId = '023484a5-f98d-4849-82e1-b7e0444b54ef';
        $vologdaTeplichnyFiasId = 'fbaca6ad-5c19-4702-a015-d1488f2ce143';
        DB::table('venues')->where('fias_id', $vologdaTeplichnyFiasId)->update(['city_fias_id' => $vologdaCityFiasId]);
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::table('venues', function (Blueprint $table) {
            $table->dropColumn('city_fias_id');
        });
    }
};
