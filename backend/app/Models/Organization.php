<?php

namespace App\Models;

use App\Models\Concerns\HasUuidPrimaryKey;
use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\Relations\BelongsToMany;
use Illuminate\Database\Eloquent\Relations\HasMany;
use Illuminate\Database\Eloquent\Relations\MorphOne;
use Illuminate\Database\Eloquent\SoftDeletes;

class Organization extends Model
{
    /** @use HasFactory<\Database\Factories\OrganizationFactory> */
    use HasFactory, HasUuidPrimaryKey, SoftDeletes;

    protected $guarded = [];

    /**
     * Access point for polymorphic organizer system.
     *
     * @return MorphOne<Organizer, $this>
     */
    public function organizer(): MorphOne
    {
        return $this->morphOne(Organizer::class, 'organizable');
    }

    /**
     * @return BelongsTo<OrganizationType, $this>
     */
    public function organizationType(): BelongsTo
    {
        return $this->belongsTo(OrganizationType::class);
    }

    /**
     * @return BelongsTo<OwnershipType, $this>
     */
    public function ownershipType(): BelongsTo
    {
        return $this->belongsTo(OwnershipType::class);
    }

    /**
     * @return BelongsTo<CoverageLevel, $this>
     */
    public function coverageLevel(): BelongsTo
    {
        return $this->belongsTo(CoverageLevel::class);
    }

    /**
     * @return BelongsToMany<ProblemCategory, $this>
     */
    public function problemCategories(): BelongsToMany
    {
        return $this->belongsToMany(ProblemCategory::class, 'organization_problem_categories');
    }

    /**
     * @return BelongsToMany<Service, $this>
     */
    public function services(): BelongsToMany
    {
        return $this->belongsToMany(Service::class, 'organization_services');
    }

    /**
     * @return BelongsToMany<Venue, $this>
     */
    public function venues(): BelongsToMany
    {
        return $this->belongsToMany(Venue::class, 'organization_venues')
            ->withPivot('is_headquarters')
            ->withTimestamps();
    }

    /**
     * Denormalized link for "events of this legal entity".
     *
     * @return HasMany<Event, $this>
     */
    public function events(): HasMany
    {
        return $this->hasMany(Event::class);
    }

    /**
     * @return HasMany<Article, $this>
     */
    public function articles(): HasMany
    {
        return $this->hasMany(Article::class);
    }

    /**
     * @return array<string, string>
     */
    protected function casts(): array
    {
        return [
            'site_urls' => 'array',
            'works_with_elderly' => 'boolean',
            'ai_confidence_score' => 'decimal:4',
            'ai_source_trace' => 'array',
            'target_audience' => 'array',
        ];
    }
}
