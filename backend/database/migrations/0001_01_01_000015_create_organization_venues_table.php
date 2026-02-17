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
        Schema::create('organization_venues', function (Blueprint $table) {
            $table->uuid('organization_id');
            $table->uuid('venue_id');
            $table->boolean('is_headquarters')->default(false);

            $table->timestamps();

            $table->primary(['organization_id', 'venue_id']);

            $table->foreign('organization_id')
                ->references('id')
                ->on('organizations')
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
        Schema::dropIfExists('organization_venues');
    }
};
