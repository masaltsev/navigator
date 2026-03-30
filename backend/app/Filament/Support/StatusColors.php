<?php

namespace App\Filament\Support;

final class StatusColors
{
    public static function badgeColor(?string $status): string
    {
        return match ($status) {
            'approved', 'published', 'scheduled' => 'success',
            'in_review', 'pending' => 'warning',
            'rejected', 'cancelled' => 'danger',
            'draft' => 'gray',
            default => 'gray',
        };
    }
}
