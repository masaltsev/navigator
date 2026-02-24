<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Add description and keywords to ontology tables for AI classification.
     */
    public function up(): void
    {
        foreach (['thematic_categories', 'services', 'organization_types', 'specialist_profiles'] as $tableName) {
            Schema::table($tableName, function (Blueprint $table) use ($tableName) {
                if (! Schema::hasColumn($tableName, 'description')) {
                    $table->text('description')->nullable()->after('name');
                }
                if (! Schema::hasColumn($tableName, 'keywords')) {
                    $table->json('keywords')->nullable()->after('description');
                }
            });
        }
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        foreach (['thematic_categories', 'services', 'organization_types', 'specialist_profiles'] as $tableName) {
            Schema::table($tableName, function (Blueprint $table) use ($tableName) {
                if (Schema::hasColumn($tableName, 'keywords')) {
                    $table->dropColumn('keywords');
                }
                if (Schema::hasColumn($tableName, 'description')) {
                    $table->dropColumn('description');
                }
            });
        }
    }
};
