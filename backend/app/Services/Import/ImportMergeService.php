<?php

namespace App\Services\Import;

use App\Models\Organization;

class ImportMergeService
{
    /**
     * Fields that can only be overwritten by a trusted source (e.g. dadata).
     * When already verified, LLM-sourced values are ignored for these fields.
     */
    private const PROTECTED_FIELDS = ['inn', 'ogrn', 'title', 'short_title'];

    /**
     * Merge incoming import attributes with existing organization data,
     * respecting verified field protection and null-safety rules.
     *
     * @param  array<string, string>|null  $existingVerified  Current verified_fields from DB
     * @param  array<string, string>|null  $incomingVerified  Verified fields from the incoming payload
     * @return array<string, mixed> Merged attributes safe for Organization::update()
     */
    public function mergeAttributes(
        Organization $existing,
        array $incoming,
        ?array $existingVerified = null,
        ?array $incomingVerified = null,
    ): array {
        $existingVerified ??= $existing->verified_fields ?? [];
        $incomingVerified ??= [];

        $merged = $incoming;

        foreach (self::PROTECTED_FIELDS as $field) {
            if (! $this->isVerifiedField($field, $existingVerified)) {
                continue;
            }

            if ($this->isVerifiedField($field, $incomingVerified)) {
                continue;
            }

            // Field is verified in DB but incoming is NOT from a trusted source — keep existing
            $merged[$field] = $existing->{$field};
        }

        $merged = $this->applyNullSafety($existing, $merged);
        $merged['verified_fields'] = $this->mergeVerifiedFields($existingVerified, $incomingVerified);

        return $merged;
    }

    /**
     * Determine the correct status for an existing organization,
     * preventing automatic downgrades of approved records.
     */
    public function resolveStatus(string $newStatus, ?string $currentStatus): string
    {
        if ($currentStatus !== 'approved') {
            return $newStatus;
        }

        if (in_array($newStatus, ['pending_review', 'draft'], true)) {
            return 'approved';
        }

        // Rejected by AI on re-crawl goes to review, not auto-reject
        if ($newStatus === 'rejected') {
            return 'pending_review';
        }

        return $newStatus;
    }

    /**
     * Don't let null/empty incoming values overwrite existing non-empty values.
     *
     * @return array<string, mixed>
     */
    private function applyNullSafety(Organization $existing, array $merged): array
    {
        $nullSafeFields = ['inn', 'ogrn', 'title', 'short_title', 'description', 'site_urls', 'target_audience'];

        foreach ($nullSafeFields as $field) {
            $incomingValue = $merged[$field] ?? null;
            $existingValue = $existing->{$field};

            if ($this->isEmpty($incomingValue) && ! $this->isEmpty($existingValue)) {
                $merged[$field] = $existingValue;
            }
        }

        return $merged;
    }

    /**
     * Merge contacts (phones, emails) from organizer level — union of unique values.
     *
     * @param  array<string>|null  $existingItems
     * @param  array<string>|null  $incomingItems
     * @return array<string>|null
     */
    public function mergeContactList(?array $existingItems, ?array $incomingItems): ?array
    {
        $existing = $existingItems ?? [];
        $incoming = $incomingItems ?? [];

        $merged = array_values(array_unique(array_merge($existing, $incoming)));

        return $merged ?: null;
    }

    /**
     * Combine existing and incoming verified_fields maps.
     * Incoming dadata entries take precedence over existing llm entries.
     *
     * @return array<string, string>
     */
    private function mergeVerifiedFields(array $existingVerified, array $incomingVerified): array
    {
        $merged = $existingVerified;

        foreach ($incomingVerified as $field => $source) {
            $currentSource = $merged[$field] ?? null;

            if ($currentSource === null || $this->sourcePriority($source) >= $this->sourcePriority($currentSource)) {
                $merged[$field] = $source;
            }
        }

        return $merged;
    }

    private function isVerifiedField(string $field, array $verifiedFields): bool
    {
        return isset($verifiedFields[$field]) && $verifiedFields[$field] !== '';
    }

    private function sourcePriority(string $source): int
    {
        return match ($source) {
            'manual' => 30,
            'dadata' => 20,
            'llm' => 10,
            default => 0,
        };
    }

    private function isEmpty(mixed $value): bool
    {
        if ($value === null) {
            return true;
        }

        if (is_string($value) && trim($value) === '') {
            return true;
        }

        if (is_array($value) && count($value) === 0) {
            return true;
        }

        return false;
    }
}
