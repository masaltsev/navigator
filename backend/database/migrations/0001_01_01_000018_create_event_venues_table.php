<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Run the migrations.
     */
    public function up(): void
    {
        Schema::create('event_venues', function (Blueprint $table) {
            $table->uuid('event_id');
            $table->uuid('venue_id');

            $table->timestamps();

            $table->primary(['event_id', 'venue_id']);

            // IMPORTANT: this FK assumes the `events` table exists before this migration runs.
            $table->foreign('event_id')
                ->references('id')
                ->on('events')
                ->cascadeOnDelete();

            $table->foreign('venue_id')
                ->references('id')
                ->on('venues')
                ->cascadeOnDelete();
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('event_venues');
    }
};
