<?php

namespace App\Models;

use App\Models\Concerns\HasUuidPrimaryKey;
use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\Relations\BelongsToMany;
use Illuminate\Database\Eloquent\SoftDeletes;

class Article extends Model
{
    /** @use HasFactory<\Database\Factories\ArticleFactory> */
    use HasFactory, HasUuidPrimaryKey, SoftDeletes;

    protected $guarded = [];

    /**
     * @deprecated Use thematicCategories() BelongsToMany instead
     *
     * @return BelongsTo<ThematicCategory, $this>
     */
    public function relatedThematicCategory(): BelongsTo
    {
        return $this->belongsTo(ThematicCategory::class, 'related_thematic_category_id');
    }

    /**
     * @deprecated Use services() BelongsToMany instead
     *
     * @return BelongsTo<Service, $this>
     */
    public function relatedService(): BelongsTo
    {
        return $this->belongsTo(Service::class, 'related_service_id');
    }

    /**
     * @return BelongsToMany<ThematicCategory, $this>
     */
    public function thematicCategories(): BelongsToMany
    {
        return $this->belongsToMany(ThematicCategory::class, 'article_thematic_category');
    }

    /**
     * @return BelongsToMany<Service, $this>
     */
    public function services(): BelongsToMany
    {
        return $this->belongsToMany(Service::class, 'article_service');
    }

    /**
     * @return BelongsToMany<SpecialistProfile, $this>
     */
    public function specialistProfiles(): BelongsToMany
    {
        return $this->belongsToMany(SpecialistProfile::class, 'article_specialist_profile');
    }

    /**
     * @return BelongsTo<Organization, $this>
     */
    public function organization(): BelongsTo
    {
        return $this->belongsTo(Organization::class);
    }

    /**
     * @return array<string, string>
     */
    protected function casts(): array
    {
        return [
            'published_at' => 'datetime',
        ];
    }
}
