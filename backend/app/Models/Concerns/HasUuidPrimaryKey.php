<?php

namespace App\Models\Concerns;

use Illuminate\Database\Eloquent\Concerns\HasUuids;

trait HasUuidPrimaryKey
{
    use HasUuids;

    // HasUuids trait from Laravel 12 already handles:
    // - $incrementing = false (via HasUniqueStringIds)
    // - $keyType = 'string' (via HasUniqueStringIds)
    // No additional properties needed
}
