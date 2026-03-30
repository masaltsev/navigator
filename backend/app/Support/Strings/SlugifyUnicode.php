<?php

namespace App\Support\Strings;

class SlugifyUnicode
{
    /**
     * Slugify while preserving unicode letters (including Cyrillic).
     */
    public static function slugifyUnicodePreserveCyrillic(string $value): string
    {
        $value = trim($value);
        if ($value === '') {
            return '';
        }

        $value = mb_strtolower($value, 'UTF-8');

        // Replace everything except letters/numbers with hyphens.
        $value = preg_replace('/[^\p{L}\p{N}]+/u', '-', (string) $value);

        $value = trim((string) $value, '-');

        return $value;
    }
}
