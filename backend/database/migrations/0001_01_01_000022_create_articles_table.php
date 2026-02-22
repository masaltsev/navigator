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
        Schema::create('articles', function (Blueprint $table) {
            $table->uuid('id')->primary();

            $table->string('title');
            $table->string('slug')->unique();

            // Content storage strategy:
            // - content_url: for external articles (links to WordPress, external CMS, etc.)
            // - content: for locally stored HTML content from WYSIWYG editors
            // This dual approach allows flexibility: migrate from external CMS gradually,
            // or keep external links while having some articles stored locally.
            $table->text('content_url')->nullable();
            $table->longText('content')->nullable();

            // SEO and presentation
            $table->text('excerpt')->nullable();
            $table->string('featured_image_url')->nullable();

            // Relationships (life situation / thematic category)
            $table->foreignId('related_thematic_category_id')
                ->nullable()
                ->constrained('thematic_categories')
                ->nullOnDelete();

            $table->foreignId('related_service_id')
                ->nullable()
                ->constrained('services')
                ->nullOnDelete();

            $table->uuid('organization_id')
                ->nullable()
                ->index();

            // Status: draft, published, archived
            $table->enum('status', ['draft', 'published', 'archived'])->default('draft')->index();

            // Publishing metadata
            $table->timestamp('published_at')->nullable()->index();

            $table->timestamps();
            $table->softDeletes();

            // Foreign key for organization (after organizations table exists)
            $table->foreign('organization_id')
                ->references('id')
                ->on('organizations')
                ->nullOnDelete();
        });

        // Note on WYSIWYG/CMS compatibility:
        // - This schema works well with Filament (filamentphp/filament) using RichEditor component
        // - Compatible with Nova (laravel/nova) RichText field
        // - For Spatie Media Library (spatie/laravel-medialibrary), add media via separate migration
        //   or use featured_image_url for simple cases
        // - For block-based editors (e.g., Tiptap with blocks), consider adding JSONB column:
        //   $table->jsonb('blocks')->nullable(); // for structured block content
        // - For full CMS features, consider integrating Statamic or similar, but this schema
        //   provides a solid foundation that can be extended.
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('articles');
    }
};
