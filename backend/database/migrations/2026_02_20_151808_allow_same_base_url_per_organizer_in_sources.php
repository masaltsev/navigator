<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Allow same base_url for different organizers; keep unique per (organizer_id, base_url).
     */
    public function up(): void
    {
        Schema::table('sources', function (Blueprint $table) {
            $table->dropUnique(['base_url']);
        });

        DB::statement('CREATE UNIQUE INDEX sources_organizer_id_base_url_unique ON sources (organizer_id, base_url) WHERE organizer_id IS NOT NULL');
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        DB::statement('DROP INDEX IF EXISTS sources_organizer_id_base_url_unique');

        Schema::table('sources', function (Blueprint $table) {
            $table->unique('base_url');
        });
    }
};
