<?php

namespace App\Models;

use App\Models\Concerns\HasUuidPrimaryKey;
use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsToMany;
use Illuminate\Database\Eloquent\SoftDeletes;
use Illuminate\Support\Facades\DB;

class Venue extends Model
{
    /** @use HasFactory<\Database\Factories\VenueFactory> */
    use HasFactory, HasUuidPrimaryKey, SoftDeletes;

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

    /**
     * Extract coordinates from PostGIS geometry point as array.
     * Returns null if coordinates are not available.
     */
    public function getCoordinatesArrayAttribute(): ?array
    {
        if (! ($this->attributes['coordinates'] ?? null)) {
            return null;
        }

        // Use raw SQL to extract lat/lng from PostGIS geometry
        $point = \DB::selectOne(
            'SELECT ST_X(coordinates::geometry) as lng, ST_Y(coordinates::geometry) as lat FROM venues WHERE id = ?',
            [$this->id]
        );

        return $point ? ['lat' => (float) $point->lat, 'lng' => (float) $point->lng] : null;
    }

    /**
     * Persist WGS84 point to PostGIS geometry column (lng, lat order for ST_MakePoint).
     */
    public function updateCoordinatesFromLatLng(?float $latitude, ?float $longitude): void
    {
        if ($latitude === null || $longitude === null) {
            return;
        }

        DB::statement(
            'UPDATE venues SET coordinates = ST_SetSRID(ST_MakePoint(?, ?), 4326)::geometry WHERE id = ?',
            [$longitude, $latitude, $this->getKey()]
        );

        $this->refresh();
    }
}
