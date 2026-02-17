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
        Schema::create('event_instances', function (Blueprint $table) {
            $table->uuid('id')->primary();

            $table->uuid('event_id')->index();

            $table->timestampTz('start_datetime');
            $table->timestampTz('end_datetime');

            $table->enum('status', ['scheduled', 'cancelled', 'rescheduled', 'finished']);

            $table->index('start_datetime');
            // Index for queries filtering by end_datetime (e.g., "events that haven't finished yet")
            $table->index('end_datetime');
            $table->index(['start_datetime', 'status']);

            $table->foreign('event_id')
                ->references('id')
                ->on('events')
                ->cascadeOnDelete();

            $table->timestamps();
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('event_instances');
    }
};
