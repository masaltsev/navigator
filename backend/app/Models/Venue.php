<?php

namespace App\Models;

use App\Models\Concerns\HasUuidPrimaryKey;
use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsToMany;

class Venue extends Model
{
    /** @use HasFactory<\Database\Factories\VenueFactory> */
    use HasFactory, HasUuidPrimaryKey;

    protected $guarded = [];

    /**
     * @return BelongsToMany<Organization, $this>
     */
    public function organizations(): BelongsToMany
    {
        return $this->belongsToMany(Organization::class, 'organization_venues')
            ->withPivot('is_headquarters')
            ->withTimestamps();
    }

    /**
     * @return BelongsToMany<Event, $this>
     */
    public function events(): BelongsToMany
    {
        return $this->belongsToMany(Event::class, 'event_venues')->withTimestamps();
    }

    /**
     * NOTE: `coordinates` is a PostGIS geometry(Point, 4326) column.
     * Without a PostGIS casting package, it is typically accessed via raw SQL.
     *
     * @return array<string, string>
     */
    protected function casts(): array
    {
        return [];
    }
}
