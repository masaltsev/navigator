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
        Schema::create('parse_profiles', function (Blueprint $table) {
            $table->uuid('id')->primary();

            $table->uuid('source_id');
            $table->string('entity_type'); // Organization, Event
            $table->string('crawl_strategy'); // list, sitemap, api_json, rss, vk_wall
            $table->jsonb('config');
            $table->boolean('is_active')->default(true);

            $table->timestamps();

            $table->foreign('source_id')
                ->references('id')
                ->on('sources')
                ->cascadeOnDelete();

            $table->index(['source_id', 'entity_type']);
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('parse_profiles');
    }
};
