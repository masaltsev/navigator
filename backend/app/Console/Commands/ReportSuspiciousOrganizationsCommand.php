<?php

namespace App\Console\Commands;

use App\Models\Organization;
use Illuminate\Console\Command;
use Illuminate\Support\Collection;
use Illuminate\Support\Facades\DB;

class ReportSuspiciousOrganizationsCommand extends Command
{
    protected $signature = 'db:report-suspicious-organizations
                            {--similar-pct=93 : Minimum similar_text() percent for fuzzy pairs (UTF-8: heuristic, review manually)}
                            {--require-prefix=0 : If > 0, fuzzy pairs must share identical first N characters after normalize}
                            {--json : Output duplicate sections as JSON lines}';

    protected $description = 'List approved organizations with suspicious titles and likely title duplicates (one side missing INN/OGRN)';

    public function handle(): int
    {
        $similarPct = max(50, min(100, (int) $this->option('similar-pct')));
        $requirePrefix = max(0, min(200, (int) $this->option('require-prefix')));
        $asJson = (bool) $this->option('json');

        $suspicious = $this->fetchSuspiciousTitles();
        $this->info('Suspicious titles (approved, not soft-deleted): '.$suspicious->count());
        if ($asJson) {
            $this->line(json_encode(['section' => 'suspicious_titles', 'rows' => $suspicious], JSON_UNESCAPED_UNICODE));
        } else {
            foreach ($suspicious->take(200) as $row) {
                $this->line(sprintf(
                    '%s | %s | inn=%s ogrn=%s | %s',
                    $row['id'],
                    $row['reason'],
                    $row['inn'] ?? '∅',
                    $row['ogrn'] ?? '∅',
                    mb_substr($row['title'], 0, 120)
                ));
            }
            if ($suspicious->count() > 200) {
                $this->warn('… truncated at 200 rows (use --json for full list)');
            }
        }

        $exactDupes = $this->fetchExactNormalizedDuplicateGroups();
        $this->info('');
        $this->info('Exact normalized title groups (≥2 orgs, mixed INN/OGRN presence): '.$exactDupes->count());
        if ($asJson) {
            $this->line(json_encode(['section' => 'exact_title_duplicates', 'groups' => $exactDupes], JSON_UNESCAPED_UNICODE));
        } else {
            foreach ($exactDupes->take(80) as $g) {
                $this->line('— '.$g['norm_title'].' ('.$g['count'].' orgs, without_leg:'.$g['without_legal_ids'].')');
                foreach ($g['orgs'] as $o) {
                    $this->line('    '.$o['id'].' | inn='.($o['inn'] ?: '∅').' ogrn='.($o['ogrn'] ?: '∅').' | '.$o['title']);
                }
            }
            if ($exactDupes->count() > 80) {
                $this->warn('… truncated at 80 groups (use --json for full list)');
            }
        }

        $fuzzyPairs = $this->fetchFuzzyDuplicatePairs($similarPct, $requirePrefix);
        $this->info('');
        $prefixNote = $requirePrefix > 0 ? ', same first '.$requirePrefix.' chars' : '';
        $this->info('Fuzzy title pairs (similar_text ≥ '.$similarPct.'%'.$prefixNote.', one without INN+OGRN, other with at least one): '.$fuzzyPairs->count());
        if ($asJson) {
            $this->line(json_encode(['section' => 'fuzzy_duplicate_pairs', 'pairs' => $fuzzyPairs], JSON_UNESCAPED_UNICODE));
        } else {
            foreach ($fuzzyPairs->take(150) as $p) {
                $this->line(sprintf(
                    '%.1f%% | no legals: %s | inn=%s ogrn=%s',
                    $p['similarity_pct'],
                    $p['without_legal_id'],
                    $p['without_inn'] ?: '∅',
                    $p['without_ogrn'] ?: '∅'
                ));
                $this->line('    with legals: '.$p['with_legal_id'].' | inn='.($p['with_inn'] ?: '∅').' ogrn='.($p['with_ogrn'] ?: '∅'));
                $this->line('    title (no legals): '.$p['title_a']);
                $this->line('    title (with legals): '.$p['title_b']);
            }
            if ($fuzzyPairs->count() > 150) {
                $this->warn('… truncated at 150 pairs (use --json for full list)');
            }
        }

        return self::SUCCESS;
    }

    /**
     * @return Collection<int, array{id: string, title: string, inn: ?string, ogrn: ?string, reason: string}>
     */
    private function fetchSuspiciousTitles(): Collection
    {
        $rows = DB::select("
            SELECT id::text AS id, title, inn, ogrn,
                CASE
                    WHEN title IS NULL OR btrim(title) = '' THEN 'empty_title'
                    WHEN char_length(btrim(title)) < 3 THEN 'title_too_short'
                    WHEN title ~* '\\\\m(test|тест|example|dummy|fake|lorem|localhost|staging|debug|sample)\\\\M' THEN 'test_like_word'
                    WHEN title ~ '[A-Za-z]{4,}' AND title !~ '[А-Яа-яЁё]' THEN 'latin_only_long'
                    WHEN title ~ '[A-Za-z]{5,}' AND title ~ '[А-Яа-яЁё]' AND title ~* '[a-z]{5,}' THEN 'mixed_latin_fragment'
                    ELSE 'other'
                END AS reason
            FROM organizations
            WHERE deleted_at IS NULL
              AND status = 'approved'
              AND (
                title IS NULL OR btrim(title) = ''
                OR char_length(btrim(title)) < 3
                OR title ~* '\\\\m(test|тест|example|dummy|fake|lorem|localhost|staging|debug|sample)\\\\M'
                OR (title ~ '[A-Za-z]{4,}' AND title !~ '[А-Яа-яЁё]')
                OR (title ~ '[A-Za-z]{5,}' AND title ~ '[А-Яа-яЁё]' AND title ~* '[a-z]{5,}')
              )
            ORDER BY updated_at DESC
        ");

        return collect($rows)->map(fn ($r) => [
            'id' => $r->id,
            'title' => $r->title,
            'inn' => $r->inn,
            'ogrn' => $r->ogrn,
            'reason' => $r->reason,
        ]);
    }

    /**
     * @return Collection<int, array{norm_title: string, count: int, without_legal_ids: int, orgs: list<array<string, mixed>>}>
     */
    private function fetchExactNormalizedDuplicateGroups(): Collection
    {
        $rows = DB::select('
            WITH o AS (
                SELECT id::text AS id, title, inn, ogrn,
                    lower(btrim(regexp_replace(title, \'\\\\s+\', \' \', \'g\'))) AS norm
                FROM organizations
                WHERE deleted_at IS NULL AND status = \'approved\'
            ),
            g AS (
                SELECT norm, count(*)::int AS cnt,
                    sum(CASE WHEN (NULLIF(btrim(inn), \'\') IS NULL AND NULLIF(btrim(ogrn), \'\') IS NULL) THEN 1 ELSE 0 END)::int AS without_leg,
                    sum(CASE WHEN (NULLIF(btrim(inn), \'\') IS NOT NULL OR NULLIF(btrim(ogrn), \'\') IS NOT NULL) THEN 1 ELSE 0 END)::int AS with_leg
                FROM o
                WHERE norm <> \'\'
                GROUP BY norm
                HAVING count(*) >= 2
                  AND sum(CASE WHEN (NULLIF(btrim(inn), \'\') IS NULL AND NULLIF(btrim(ogrn), \'\') IS NULL) THEN 1 ELSE 0 END) >= 1
                  AND sum(CASE WHEN (NULLIF(btrim(inn), \'\') IS NOT NULL OR NULLIF(btrim(ogrn), \'\') IS NOT NULL) THEN 1 ELSE 0 END) >= 1
            )
            SELECT g.norm, g.cnt, g.without_leg,
                json_agg(json_build_object(
                    \'id\', o.id,
                    \'title\', o.title,
                    \'inn\', o.inn,
                    \'ogrn\', o.ogrn
                ) ORDER BY o.inn NULLS LAST, o.ogrn NULLS LAST) AS orgs
            FROM g
            JOIN o ON o.norm = g.norm
            GROUP BY g.norm, g.cnt, g.without_leg
            ORDER BY g.cnt DESC, g.norm
        ');

        return collect($rows)->map(fn ($r) => [
            'norm_title' => $r->norm,
            'count' => (int) $r->cnt,
            'without_legal_ids' => (int) $r->without_leg,
            'orgs' => json_decode($r->orgs, true),
        ]);
    }

    /**
     * @return Collection<int, array<string, mixed>>
     */
    private function fetchFuzzyDuplicatePairs(int $similarPct, int $requirePrefixChars): Collection
    {
        $orgs = Organization::query()
            ->whereNull('deleted_at')
            ->where('status', 'approved')
            ->orderBy('id')
            ->get(['id', 'title', 'inn', 'ogrn']);

        $enriched = $orgs->map(function (Organization $o) {
            $n = $this->normalizeTitle((string) $o->title);

            return [
                'id' => (string) $o->id,
                'title' => (string) $o->title,
                'norm' => $n,
                'has_legal' => $this->hasLegalIds($o->inn, $o->ogrn),
                'inn' => $o->inn,
                'ogrn' => $o->ogrn,
                'bucket' => $n === '' ? '' : mb_substr($n, 0, 10),
            ];
        })->filter(fn (array $r) => $r['norm'] !== '' && mb_strlen($r['norm']) >= 8);

        $pairs = collect();
        foreach ($enriched->groupBy('bucket') as $bucket => $group) {
            if ($bucket === '' || $group->count() < 2) {
                continue;
            }
            $list = $group->values()->all();
            $n = count($list);
            for ($i = 0; $i < $n; $i++) {
                for ($j = $i + 1; $j < $n; $j++) {
                    $a = $list[$i];
                    $b = $list[$j];
                    if ($a['has_legal'] === $b['has_legal']) {
                        continue;
                    }
                    if ($requirePrefixChars > 0) {
                        $p1 = mb_substr($a['norm'], 0, $requirePrefixChars);
                        $p2 = mb_substr($b['norm'], 0, $requirePrefixChars);
                        if ($p1 !== $p2) {
                            continue;
                        }
                    }
                    similar_text($a['norm'], $b['norm'], $pct);
                    if ($pct < $similarPct) {
                        continue;
                    }
                    $without = $a['has_legal'] ? $b : $a;
                    $with = $a['has_legal'] ? $a : $b;
                    $pairs->push([
                        'similarity_pct' => round($pct, 1),
                        'without_legal_id' => $without['id'],
                        'without_inn' => $without['inn'],
                        'without_ogrn' => $without['ogrn'],
                        'with_legal_id' => $with['id'],
                        'with_inn' => $with['inn'],
                        'with_ogrn' => $with['ogrn'],
                        'title_a' => $without['title'],
                        'title_b' => $with['title'],
                    ]);
                }
            }
        }

        return $pairs->unique(fn (array $p) => min($p['without_legal_id'], $p['with_legal_id']).':'.max($p['without_legal_id'], $p['with_legal_id']))
            ->sortByDesc('similarity_pct')
            ->values();
    }

    private function normalizeTitle(string $title): string
    {
        $t = mb_strtolower(trim($title));

        return preg_replace('/\s+/u', ' ', $t) ?? $t;
    }

    private function hasLegalIds(?string $inn, ?string $ogrn): bool
    {
        $inn = $inn !== null ? trim($inn) : '';
        $ogrn = $ogrn !== null ? trim($ogrn) : '';

        return $inn !== '' || $ogrn !== '';
    }
}
