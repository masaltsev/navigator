<?php

namespace App\Models;

use App\Models\Concerns\HasUuidPrimaryKey;
use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\HasMany;
use Illuminate\Database\Eloquent\SoftDeletes;

class Source extends Model
{
    /** @use HasFactory<\Database\Factories\SourceFactory> */
    use HasFactory, HasUuidPrimaryKey, SoftDeletes;

    protected $guarded = [];

    /**
     * Parse profiles associated with this source.
     *
     * @return HasMany<ParseProfile, $this>
     */
    public function parseProfiles(): HasMany
    {
        return $this->hasMany(ParseProfile::class);
    }

    /**
     * @return array<string, string>
     */
    protected function casts(): array
    {
        return [
            'entry_points' => 'array',
            'is_active' => 'boolean',
            'last_crawled_at' => 'datetime',
        ];
    }
}
