<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('article_thematic_category', function (Blueprint $table) {
            $table->uuid('article_id');
            $table->unsignedBigInteger('thematic_category_id');
            $table->primary(['article_id', 'thematic_category_id']);
            $table->foreign('article_id')->references('id')->on('articles')->cascadeOnDelete();
            $table->foreign('thematic_category_id')->references('id')->on('thematic_categories')->cascadeOnDelete();
        });

        Schema::create('article_service', function (Blueprint $table) {
            $table->uuid('article_id');
            $table->unsignedBigInteger('service_id');
            $table->primary(['article_id', 'service_id']);
            $table->foreign('article_id')->references('id')->on('articles')->cascadeOnDelete();
            $table->foreign('service_id')->references('id')->on('services')->cascadeOnDelete();
        });

        Schema::create('article_specialist_profile', function (Blueprint $table) {
            $table->uuid('article_id');
            $table->unsignedBigInteger('specialist_profile_id');
            $table->primary(['article_id', 'specialist_profile_id']);
            $table->foreign('article_id')->references('id')->on('articles')->cascadeOnDelete();
            $table->foreign('specialist_profile_id')->references('id')->on('specialist_profiles')->cascadeOnDelete();
        });

        DB::statement('
            INSERT INTO article_thematic_category (article_id, thematic_category_id)
            SELECT id, related_thematic_category_id
            FROM articles
            WHERE related_thematic_category_id IS NOT NULL
        ');

        DB::statement('
            INSERT INTO article_service (article_id, service_id)
            SELECT id, related_service_id
            FROM articles
            WHERE related_service_id IS NOT NULL
        ');
    }

    public function down(): void
    {
        Schema::dropIfExists('article_specialist_profile');
        Schema::dropIfExists('article_service');
        Schema::dropIfExists('article_thematic_category');
    }
};
