<?php

namespace App\Models;

use App\Models\Concerns\HasUuidPrimaryKey;
use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\Relations\BelongsToMany;
use Illuminate\Database\Eloquent\Relations\HasMany;

class Event extends Model
{
    /** @use HasFactory<\Database\Factories\EventFactory> */
    use HasFactory, HasUuidPrimaryKey;

    protected $guarded = [];

    /**
     * Polymorphic organizer router (Organization / InitiativeGroup / Individual).
     *
     * @return BelongsTo<Organizer, $this>
     */
    public function organizer(): BelongsTo
    {
        return $this->belongsTo(Organizer::class);
    }

    /**
     * Denormalized link for the common query “events of this legal entity”.
     *
     * @return BelongsTo<Organization, $this>
     */
    public function organization(): BelongsTo
    {
        return $this->belongsTo(Organization::class);
    }

    /**
     * Materialized instances generated from `rrule_string`.
     *
     * @return HasMany<EventInstance, $this>
     */
    public function instances(): HasMany
    {
        return $this->hasMany(EventInstance::class);
    }

    /**
     * @return BelongsToMany<Venue, $this>
     */
    public function venues(): BelongsToMany
    {
        return $this->belongsToMany(Venue::class, 'event_venues')->withTimestamps();
    }

    /**
     * Dictionary categories (lectures, workshops, etc.).
     *
     * @return BelongsToMany<EventCategory, $this>
     */
    public function categories(): BelongsToMany
    {
        return $this->belongsToMany(EventCategory::class, 'event_event_categories');
    }

    /**
     * @return array<string, string>
     */
    protected function casts(): array
    {
        return [
            'target_audience' => 'array',
            'ai_confidence_score' => 'decimal:4',
            'ai_source_trace' => 'array',
        ];
    }
}
