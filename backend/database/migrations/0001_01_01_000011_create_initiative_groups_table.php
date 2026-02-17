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
        Schema::create('initiative_groups', function (Blueprint $table) {
            $table->uuid('id')->primary();

            $table->string('name');
            $table->text('description')->nullable();
            $table->string('community_focus')->nullable();
            $table->date('established_date')->nullable();

            $table->boolean('works_with_elderly')->default(false)->index();
            $table->decimal('ai_confidence_score', 8, 4)->nullable();
            $table->text('ai_explanation')->nullable();
            $table->jsonb('ai_source_trace')->nullable();

            $table->jsonb('target_audience')->nullable();

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
        Schema::dropIfExists('initiative_groups');
    }
};
