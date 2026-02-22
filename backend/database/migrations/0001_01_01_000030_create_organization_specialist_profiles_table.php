<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Run the migrations.
     *
     * Pivot: organizations <-> specialist_profiles.
     */
    public function up(): void
    {
        Schema::create('organization_specialist_profiles', function (Blueprint $table) {
            $table->uuid('organization_id');
            $table->foreignId('specialist_profile_id');

            $table->primary(['organization_id', 'specialist_profile_id']);

            $table->foreign('organization_id')
                ->references('id')
                ->on('organizations')
                ->cascadeOnDelete();

            $table->foreign('specialist_profile_id')
                ->references('id')
                ->on('specialist_profiles')
                ->cascadeOnDelete();
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('organization_specialist_profiles');
    }
};
