<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Stores AI-suggested taxonomy terms that don't match existing dictionaries.
     * Moderators review and either add to official dictionaries or dismiss.
     */
    public function up(): void
    {
        Schema::create('suggested_taxonomy_items', function (Blueprint $table) {
            $table->uuid('id')->primary();

            $table->uuid('organization_id')->index();
            $table->string('source_reference')->nullable()->index();

            $table->string('dictionary_type')->index();
            $table->string('suggested_name');
            $table->text('ai_reasoning')->nullable();

            $table->string('status')->default('pending')->index();

            $table->foreign('organization_id')
                ->references('id')
                ->on('organizations')
                ->cascadeOnDelete();

            $table->timestamps();
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('suggested_taxonomy_items');
    }
};
