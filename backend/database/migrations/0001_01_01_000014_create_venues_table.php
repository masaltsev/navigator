<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Run the migrations.
     */
    public function up(): void
    {
        Schema::create('venues', function (Blueprint $table) {
            $table->uuid('id')->primary();

            $table->string('address_raw');
            $table->string('fias_id')->nullable()->index();
            $table->string('kladr_id')->nullable()->index();
            $table->string('region_iso')->nullable()->index();

            // PostGIS geometry(Point, 4326) will be added via raw SQL below.

            $table->timestamps();
            $table->softDeletes();
        });

        // Option A (chosen): PostGIS geometry(Point, 4326) via raw SQL.
        DB::statement('ALTER TABLE venues ADD COLUMN coordinates geometry(Point, 4326)');
        DB::statement('CREATE INDEX venues_coordinates_gist_idx ON venues USING GIST (coordinates)');

        // Note: a composite index like (status, coordinates) does not apply here because venues has no status column.
        // If you need geo+status filtering, add appropriate indexes on the table that owns "status" (e.g. event_instances)
        // and keep the GiST index on venues.coordinates.
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('venues');
    }
};
