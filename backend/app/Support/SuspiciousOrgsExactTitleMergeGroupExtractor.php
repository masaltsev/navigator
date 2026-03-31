<?php

namespace App\Support;

/**
 * Parses backend/suspicious-orgs.json (mixed text + JSON tail) and returns
 * merge pairs for the "exact_title_duplicates" section:
 * merge organizations without INN/OGRN into the single canonical org that has legal ids.
 */
final class SuspiciousOrgsExactTitleMergeGroupExtractor
{
    /**
     * @return list<array{duplicate_id: string, canonical_id: string, norm_title: string}>
     */
    public static function mergePairsFromReportFile(string $path): array
    {
        $raw = @file_get_contents($path);
        if ($raw === false) {
            throw new \InvalidArgumentException("Cannot read file: {$path}");
        }

        if (! preg_match('/"exact_title_duplicates"\s*,\s*"groups"\s*:\s*(\[[\s\S]*\])\s*\}\s*\n\nFuzzy/sm', $raw, $m)) {
            throw new \InvalidArgumentException('Could not extract exact_title_duplicates groups from report.');
        }

        $groups = json_decode($m[1], true);
        if (! is_array($groups)) {
            throw new \InvalidArgumentException('Invalid groups JSON.');
        }

        $out = [];
        foreach ($groups as $g) {
            if (! is_array($g)) {
                continue;
            }
            $normTitle = (string) ($g['norm_title'] ?? '');
            $orgs = $g['orgs'] ?? [];
            if (! is_array($orgs) || $orgs === []) {
                continue;
            }

            $canon = [];
            $dups = [];
            foreach ($orgs as $o) {
                if (! is_array($o)) {
                    continue;
                }
                $inn = trim((string) ($o['inn'] ?? ''));
                $ogrn = trim((string) ($o['ogrn'] ?? ''));
                $id = (string) ($o['id'] ?? '');
                if ($id === '') {
                    continue;
                }
                if ($inn !== '' || $ogrn !== '') {
                    $canon[] = $id;
                } else {
                    $dups[] = $id;
                }
            }

            // Only auto-merge the safe shape: exactly one canonical with legal ids.
            if (count($canon) !== 1 || count($dups) < 1) {
                continue;
            }

            foreach ($dups as $dupId) {
                $out[] = [
                    'duplicate_id' => $dupId,
                    'canonical_id' => $canon[0],
                    'norm_title' => $normTitle,
                ];
            }
        }

        // Deduplicate (just in case).
        $byKey = [];
        foreach ($out as $p) {
            $k = $p['duplicate_id'].'|'.$p['canonical_id'];
            $byKey[$k] = $p;
        }

        return array_values($byKey);
    }
}
