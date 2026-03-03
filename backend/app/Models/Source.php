<?php

namespace App\Models;

use App\Models\Concerns\HasUuidPrimaryKey;
use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\Relations\HasMany;
use Illuminate\Database\Eloquent\SoftDeletes;

class Source extends Model
{
    /** @use HasFactory<\Database\Factories\SourceFactory> */
    use HasFactory, HasUuidPrimaryKey, SoftDeletes;

    protected $guarded = [];

    /**
     * All allowed source kinds (filter + update).
     * Aggregator kinds: registry_fpg, registry_sonko, platform_silverage (from aggregator pipelines).
     * Event aggregator kinds: event_aggregator, platform_silverage_events, afisha (for event harvest policy).
     */
    public const KINDS = [
        'org_website',
        'vk_group',
        'ok_group',
        'tg_channel',
        'registry_sfr',
        'registry_minsoc',
        'api_json',
        'registry_fpg',
        'registry_sonko',
        'platform_silverage',
        'event_aggregator',
        'platform_silverage_events',
        'afisha',
    ];

    /** Kinds that can be created via POST /sources (Harvester + UI). */
    public const KINDS_CREATABLE = [
        'org_website',
        'vk_group',
        'ok_group',
        'tg_channel',
        'registry_fpg',
        'registry_sonko',
        'platform_silverage',
        'event_aggregator',
        'platform_silverage_events',
        'afisha',
    ];

    /**
     * Organizer this source belongs to (for kind=org_website: site of that organizer).
     * Enables Harvester to know which organizer to update when pushing enriched data.
     *
     * @return BelongsTo<Organizer, $this>
     */
    public function organizer(): BelongsTo
    {
        return $this->belongsTo(Organizer::class);
    }

    /**
     * Scope: sources due for crawling (is_active, not deleted, organizer_id set,
     * and last_crawled_at is null or past crawl_period_days).
     */
    public function scopeDue($query)
    {
        return $query
            ->where('is_active', true)
            ->whereNull('deleted_at')
            ->whereNotNull('organizer_id')
            ->where(function ($q) {
                $q->whereNull('last_crawled_at')
                    ->orWhereRaw('(last_crawled_at + (crawl_period_days || \' days\')::interval) <= ?', [now()]);
            })
            ->orderByRaw('last_crawled_at ASC NULLS FIRST')
            ->orderByDesc('created_at');
    }

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
