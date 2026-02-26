<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Short display name for cards/lists (e.g. "КЦСОН Вологда" instead of full legal title).
     * AI pipeline already sends this field, but ImportController was not persisting it.
     */
    public function up(): void
    {
        Schema::table('organizations', function (Blueprint $table) {
            $table->string('short_title', 100)->nullable()->after('title');
        });
    }

    public function down(): void
    {
        Schema::table('organizations', function (Blueprint $table) {
            $table->dropColumn('short_title');
        });
    }
};
