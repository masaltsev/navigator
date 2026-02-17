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
        Schema::create('sources', function (Blueprint $table) {
            $table->uuid('id')->primary();

            $table->string('name');
            $table->string('kind'); // registry_sfr, registry_minsoc, org_website, vk_group, tg_channel, api_json
            $table->string('region_iso')->nullable();
            $table->uuid('fias_region_id')->nullable();
            $table->text('base_url')->unique();
            $table->jsonb('entry_points')->default('[]');
            $table->uuid('parse_profile_id')->nullable();
            $table->integer('crawl_period_days')->default(7);
            $table->timestampTz('last_crawled_at')->nullable();
            $table->string('last_status')->default('pending');
            $table->integer('priority')->default(50);
            $table->boolean('is_active')->default(true);

            $table->timestamps();
            $table->softDeletes();

            $table->index('kind');
            $table->index('last_status');
            $table->index('is_active');
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('sources');
    }
};
