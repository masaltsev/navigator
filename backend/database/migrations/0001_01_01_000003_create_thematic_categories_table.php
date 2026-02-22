<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Run the migrations.
     *
     * Life situations (formerly problem_categories). Hierarchical, Positive Aging naming.
     */
    public function up(): void
    {
        Schema::create('thematic_categories', function (Blueprint $table) {
            $table->id();

            $table->string('name')->index();
            $table->string('code')->unique();
            $table->boolean('is_active')->default(true);

            $table->foreignId('parent_id')
                ->nullable()
                ->constrained('thematic_categories')
                ->nullOnDelete();

            $table->timestamps();
            $table->softDeletes();
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('thematic_categories');
    }
};
