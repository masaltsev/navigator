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
        Schema::create('organizations', function (Blueprint $table) {
            $table->uuid('id')->primary();

            $table->string('title');
            $table->text('description')->nullable();

            $table->string('inn')->nullable()->index()->unique();
            $table->string('ogrn')->nullable()->index()->unique();

            $table->jsonb('site_urls')->nullable();

            $table->foreignId('organization_type_id')
                ->nullable()
                ->constrained('organization_types')
                ->nullOnDelete();

            $table->foreignId('ownership_type_id')
                ->nullable()
                ->constrained('ownership_types')
                ->nullOnDelete();

            $table->foreignId('coverage_level_id')
                ->nullable()
                ->constrained('coverage_levels')
                ->nullOnDelete();

            $table->boolean('works_with_elderly')->default(false)->index();
            $table->decimal('ai_confidence_score', 8, 4)->nullable();
            $table->text('ai_explanation')->nullable();
            $table->jsonb('ai_source_trace')->nullable();

            $table->jsonb('target_audience')->nullable();

            $table->bigInteger('vk_group_id')->nullable()->index();
            $table->bigInteger('ok_group_id')->nullable()->index();

            $table->string('status')->index();

            $table->timestamps();
            $table->softDeletes();
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('organizations');
    }
};
