<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Run the migrations.
     *
     * Pivot: organizations <-> organization_types (M:N).
     */
    public function up(): void
    {
        Schema::create('organization_organization_types', function (Blueprint $table) {
            $table->uuid('organization_id');
            $table->foreignId('organization_type_id');

            $table->primary(['organization_id', 'organization_type_id']);

            $table->foreign('organization_id')
                ->references('id')
                ->on('organizations')
                ->cascadeOnDelete();

            $table->foreign('organization_type_id')
                ->references('id')
                ->on('organization_types')
                ->cascadeOnDelete();
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('organization_organization_types');
    }
};
