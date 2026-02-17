<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsToMany;
use Illuminate\Database\Eloquent\SoftDeletes;

class EventCategory extends Model
{
    /** @use HasFactory<\Database\Factories\EventCategoryFactory> */
    use HasFactory, SoftDeletes;

    protected $guarded = [];

    // Note: Both 'slug' and 'code' fields exist. 'slug' is URL-friendly, 'code' is semantic identifier.
    // TODO: Decide which identifier to use consistently in AI pipeline and update ImportController accordingly.

    /**
     * Pivot table is `event_event_categories` to avoid collision with dictionary table name.
     *
     * @return BelongsToMany<Event, $this>
     */
    public function events(): BelongsToMany
    {
        return $this->belongsToMany(Event::class, 'event_event_categories');
    }
}
