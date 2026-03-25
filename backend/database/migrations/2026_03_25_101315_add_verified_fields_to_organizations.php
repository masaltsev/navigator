<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::table('organizations', function (Blueprint $table) {
            $table->jsonb('verified_fields')->nullable()->after('source_reference');
            $table->string('content_hash', 32)->nullable()->after('verified_fields');
        });
    }

    public function down(): void
    {
        Schema::table('organizations', function (Blueprint $table) {
            $table->dropColumn(['verified_fields', 'content_hash']);
        });
    }
};

