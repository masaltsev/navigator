<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Run the migrations.
     *
     * Pivot: organizations <-> thematic_categories (life situations).
     */
    public function up(): void
    {
        Schema::create('organization_thematic_categories', function (Blueprint $table) {
            $table->uuid('organization_id');
            $table->foreignId('thematic_category_id');

            $table->primary(['organization_id', 'thematic_category_id']);

            $table->foreign('organization_id')
                ->references('id')
                ->on('organizations')
                ->cascadeOnDelete();

            $table->foreign('thematic_category_id')
                ->references('id')
                ->on('thematic_categories')
                ->cascadeOnDelete();
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('organization_thematic_categories');
    }
};
