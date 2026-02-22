<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Run the migrations.
     *
     * Links source to organizer for org_website sources so Harvester knows
     * which organizer to update when pushing enriched data.
     */
    public function up(): void
    {
        Schema::table('sources', function (Blueprint $table) {
            $table->uuid('organizer_id')->nullable()->after('id');
            $table->foreign('organizer_id')
                ->references('id')
                ->on('organizers')
                ->nullOnDelete();
            $table->index('organizer_id');
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::table('sources', function (Blueprint $table) {
            $table->dropForeign(['organizer_id']);
            $table->dropColumn('organizer_id');
        });
    }
};
