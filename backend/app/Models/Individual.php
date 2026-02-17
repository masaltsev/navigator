<?php

namespace App\Models;

use App\Models\Concerns\HasUuidPrimaryKey;
use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\MorphOne;
use Illuminate\Database\Eloquent\SoftDeletes;

class Individual extends Model
{
    /** @use HasFactory<\Database\Factories\IndividualFactory> */
    use HasFactory, HasUuidPrimaryKey, SoftDeletes;

    protected $guarded = [];

    /**
     * Access point for polymorphic organizer system.
     *
     * Events are attached to the related `Organizer` (see Organizer::events()).
     *
     * @return MorphOne<Organizer, $this>
     */
    public function organizer(): MorphOne
    {
        return $this->morphOne(Organizer::class, 'organizable');
    }

    /**
     * @return array<string, string>
     */
    protected function casts(): array
    {
        return [
            'consent_given' => 'boolean',
        ];
    }
}
