<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Add description and keywords to ownership_types for AI classification.
     */
    public function up(): void
    {
        Schema::table('ownership_types', function (Blueprint $table) {
            if (! Schema::hasColumn('ownership_types', 'description')) {
                $table->text('description')->nullable()->after('name');
            }
            if (! Schema::hasColumn('ownership_types', 'keywords')) {
                $table->json('keywords')->nullable()->after('description');
            }
        });
    }

    public function down(): void
    {
        Schema::table('ownership_types', function (Blueprint $table) {
            if (Schema::hasColumn('ownership_types', 'keywords')) {
                $table->dropColumn('keywords');
            }
            if (Schema::hasColumn('ownership_types', 'description')) {
                $table->dropColumn('description');
            }
        });
    }
};
