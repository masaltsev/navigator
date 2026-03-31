<?php

namespace App\Support;

/**
 * Parses backend/suspicious-orgs.json (mixed text + JSON tail) and returns
 * deduplicated fuzzy duplicate pairs approved for merge (dup → canonical with INN/OGRN).
 */
final class SuspiciousOrgsFuzzyMergePairExtractor
{
    /**
     * @return list<array{
     *     similarity_pct: float,
     *     without_legal_id: string,
     *     with_legal_id: string,
     *     with_inn: ?string,
     *     with_ogrn: ?string,
     *     title_a: string,
     *     title_b: string
     * }>
     */
    public static function mergePairsFromReportFile(string $path): array
    {
        $raw = @file_get_contents($path);
        if ($raw === false) {
            throw new \InvalidArgumentException("Cannot read file: {$path}");
        }

        if (! preg_match('/"fuzzy_duplicate_pairs"\s*,\s*"pairs"\s*:\s*(\[[\s\S]*\])\s*\}\s*$/m', $raw, $m)) {
            throw new \InvalidArgumentException('Could not extract fuzzy_duplicate_pairs JSON from report.');
        }

        $pairs = json_decode($m[1], true);
        if (! is_array($pairs)) {
            throw new \InvalidArgumentException('Invalid pairs JSON.');
        }

        $merge = [];
        foreach ($pairs as $p) {
            if (! is_array($p)) {
                continue;
            }
            if (self::shouldExclude($p)) {
                continue;
            }
            $merge[] = $p;
        }

        $byDup = [];
        foreach ($merge as $p) {
            $k = ($p['without_legal_id'] ?? '').'|'.($p['with_legal_id'] ?? '');
            if ($k === '|') {
                continue;
            }
            if (! isset($byDup[$k]) || (float) ($p['similarity_pct'] ?? 0) > (float) ($byDup[$k]['similarity_pct'] ?? 0)) {
                $byDup[$k] = $p;
            }
        }

        $mergeUnique = array_values($byDup);
        usort($mergeUnique, fn ($a, $b) => ((float) ($b['similarity_pct'] ?? 0)) <=> ((float) ($a['similarity_pct'] ?? 0)));

        return $mergeUnique;
    }

    /**
     * @param  array<string, mixed>  $p
     */
    private static function shouldExclude(array $p): bool
    {
        $ta = (string) ($p['title_a'] ?? '');
        $tb = (string) ($p['title_b'] ?? '');

        if (self::normalizeForMatch($ta) === self::normalizeForMatch($tb)) {
            return false;
        }

        if (self::isMedicalContext($ta) && self::isMedicalContext($tb)) {
            if (self::normalizeForMatch($ta) !== self::normalizeForMatch($tb)) {
                return true;
            }
        }

        if (self::templateDifferentRegion($ta, $tb)) {
            return true;
        }

        $na = self::normalizeForMatch($ta);
        $nb = self::normalizeForMatch($tb);
        if ((preg_match('/\bсклад\b/u', $na) && preg_match('/\bфонд\b/u', $nb))
            || (preg_match('/\bфонд\b/u', $na) && preg_match('/\bсклад\b/u', $nb))) {
            return true;
        }

        if (preg_match('/автономная некоммерческая|центр социального обслуживания|благотворительный фонд/u', $na)) {
            if (self::quotedSignatureDiffers($ta, $tb)) {
                return true;
            }
        }

        if (preg_match('/^тос\s/u', $na) && self::quotedSignatureDiffers($ta, $tb)) {
            return true;
        }

        return false;
    }

    private static function normalizeForMatch(string $s): string
    {
        $s = mb_strtolower($s);

        return preg_replace('/\s+/u', ' ', trim($s)) ?? $s;
    }

    private static function isMedicalContext(string $t): bool
    {
        $n = self::normalizeForMatch($t);

        return (bool) preg_match(
            '/больниц|поликлиник|медико[\s\-]?санитарн|медсанчаст|госпитал|црб|клиническ(ая|ой|ую)?\s+(больниц|поликлиник)|гбуз|буз\s|фгбуз|бюджетное учреждение здравоохранения|гбу\s*з|гбуц|спб гбуз|городская поликлиника|областная больница|районная больниц|межрайонн|цгб|ммц|медицинск/u',
            $n
        );
    }

    /** @return list<string> */
    private static function extractQuotedFragments(string $t): array
    {
        $out = [];
        if (preg_match_all('/«([^»]{2,80})»/u', $t, $m)) {
            $out = array_merge($out, $m[1]);
        }
        if (preg_match_all('/"([^"]{2,80})"/u', $t, $m2)) {
            $out = array_merge($out, $m2[1]);
        }

        return $out;
    }

    private static function quotedSignatureDiffers(string $a, string $b): bool
    {
        $qa = self::extractQuotedFragments($a);
        $qb = self::extractQuotedFragments($b);
        if ($qa === [] || $qb === []) {
            return false;
        }
        $la = self::normalizeForMatch(end($qa));
        $lb = self::normalizeForMatch(end($qb));

        return $la !== '' && $lb !== '' && $la !== $lb;
    }

    private static function templateDifferentRegion(string $a, string $b): bool
    {
        $na = self::normalizeForMatch($a);
        $nb = self::normalizeForMatch($b);
        if ($na === $nb) {
            return false;
        }
        $volMed = '/волонт[её]ры?-медики\s*\|\s*(.+)$/u';
        if (preg_match($volMed, $na, $ma) && preg_match($volMed, $nb, $mb)) {
            return self::normalizeForMatch(trim($ma[1])) !== self::normalizeForMatch(trim($mb[1]));
        }
        if (preg_match('/региональный центр «серебряного» добровольчества\s+(.+)$/u', $na, $ma)
            && preg_match('/региональный центр «серебряного» добровольчества\s+(.+)$/u', $nb, $mb)) {
            return trim($ma[1]) !== trim($mb[1]);
        }
        if (preg_match('/филиал российского общества\s*[«"]знание[»"]\s*(.+)$/u', $na, $ma)
            && preg_match('/филиал российского общества\s*[«"]знание[»"]\s*(.+)$/u', $nb, $mb)) {
            return trim($ma[1]) !== trim($mb[1]);
        }

        return false;
    }
}
