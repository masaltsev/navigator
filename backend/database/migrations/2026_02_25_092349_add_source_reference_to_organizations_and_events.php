<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Adds source_reference to organizations and events for AI-pipeline deduplication.
     *
     * Without this field, organizations without INN (most NGOs, initiative groups)
     * cannot be matched on re-import, causing duplicates on every batch run.
     * Events have no natural key at all — source_reference is the only viable match key.
     */
    public function up(): void
    {
        Schema::table('organizations', function (Blueprint $table) {
            $table->string('source_reference')->nullable()->after('status')->index();
        });

        Schema::table('events', function (Blueprint $table) {
            $table->string('source_reference')->nullable()->after('status')->index();
        });
    }

    public function down(): void
    {
        Schema::table('organizations', function (Blueprint $table) {
            $table->dropIndex(['source_reference']);
            $table->dropColumn('source_reference');
        });

        Schema::table('events', function (Blueprint $table) {
            $table->dropIndex(['source_reference']);
            $table->dropColumn('source_reference');
        });
    }
};
