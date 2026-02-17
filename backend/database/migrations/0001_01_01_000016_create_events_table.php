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
        Schema::create('events', function (Blueprint $table) {
            $table->uuid('id')->primary();

            $table->uuid('organizer_id')->index();
            $table->uuid('organization_id')->nullable()->index();

            $table->string('title');
            $table->text('description')->nullable();

            $table->enum('attendance_mode', ['offline', 'online', 'mixed']);
            $table->string('online_url')->nullable();

            $table->string('rrule_string')->nullable();

            $table->jsonb('target_audience')->nullable();

            $table->decimal('ai_confidence_score', 8, 4)->nullable();
            $table->text('ai_explanation')->nullable();
            $table->jsonb('ai_source_trace')->nullable();

            $table->string('status')->index();

            // Composite index for common public API filter: status='approved' AND attendance_mode IN (...)
            $table->index(['status', 'attendance_mode']);

            $table->foreign('organizer_id')
                ->references('id')
                ->on('organizers')
                ->cascadeOnDelete();

            $table->foreign('organization_id')
                ->references('id')
                ->on('organizations')
                ->nullOnDelete();

            $table->timestamps();
            $table->softDeletes();
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('events');
    }
};
