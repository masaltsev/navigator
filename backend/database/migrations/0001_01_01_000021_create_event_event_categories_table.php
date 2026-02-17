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
        Schema::create('event_event_categories', function (Blueprint $table) {
            $table->uuid('event_id');
            $table->foreignId('event_category_id');

            $table->primary(['event_id', 'event_category_id']);

            $table->foreign('event_id')
                ->references('id')
                ->on('events')
                ->cascadeOnDelete();

            $table->foreign('event_category_id')
                ->references('id')
                ->on('event_categories')
                ->cascadeOnDelete();
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('event_event_categories');
    }
};
