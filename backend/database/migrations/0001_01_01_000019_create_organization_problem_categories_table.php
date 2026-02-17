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
        Schema::create('organization_problem_categories', function (Blueprint $table) {
            $table->uuid('organization_id');
            $table->foreignId('problem_category_id');

            $table->primary(['organization_id', 'problem_category_id']);

            $table->foreign('organization_id')
                ->references('id')
                ->on('organizations')
                ->cascadeOnDelete();

            $table->foreign('problem_category_id')
                ->references('id')
                ->on('problem_categories')
                ->cascadeOnDelete();
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('organization_problem_categories');
    }
};
