<?php

/**
 * One-off: read backend/suspicious-orgs.json (mixed text + JSON tail), filter fuzzy pairs.
 * Not loaded by Laravel autoload.
 */
$path = dirname(__DIR__).'/suspicious-orgs.json';
$raw = file_get_contents($path);
if ($raw === false) {
    fwrite(STDERR, "Cannot read $path\n");
    exit(1);
}

if (! preg_match('/"fuzzy_duplicate_pairs"\s*,\s*"pairs"\s*:\s*(\[[\s\S]*\])\s*\}\s*$/m', $raw, $m)) {
    fwrite(STDERR, "Could not extract fuzzy_duplicate_pairs JSON\n");
    exit(1);
}

$pairs = json_decode($m[1], true);
if (! is_array($pairs)) {
    fwrite(STDERR, "Invalid JSON\n");
    exit(1);
}

function normalizeForMatch(string $s): string
{
    $s = mb_strtolower($s);

    return preg_replace('/\s+/u', ' ', trim($s)) ?? $s;
}

function isMedicalContext(string $t): bool
{
    $n = normalizeForMatch($t);

    return (bool) preg_match(
        '/больниц|поликлиник|медико[\s\-]?санитарн|медсанчаст|госпитал|црб|клиническ(ая|ой|ую)?\s+(больниц|поликлиник)|гбуз|буз\s|фгбуз|бюджетное учреждение здравоохранения|гбу\s*з|гбуц|спб гбуз|городская поликлиника|областная больница|районная больниц|межрайонн|цгб|ммц|медицинск/u',
        $n
    );
}

/** @return list<int> */
function extractFacilityNumbers(string $t): array
{
    $nums = [];
    if (preg_match_all('/(?:№|n|N)\s*(\d+)/u', $t, $m)) {
        foreach ($m[1] as $d) {
            $nums[] = (int) $d;
        }
    }

    return array_values(array_unique($nums));
}

/** @return list<string> */
function extractQuotedFragments(string $t): array
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

function quotedSignatureDiffers(string $a, string $b): bool
{
    $qa = extractQuotedFragments($a);
    $qb = extractQuotedFragments($b);
    if ($qa === [] || $qb === []) {
        return false;
    }
    $la = normalizeForMatch(end($qa));
    $lb = normalizeForMatch(end($qb));

    return $la !== '' && $lb !== '' && $la !== $lb;
}

function templateDifferentRegion(string $a, string $b): bool
{
    $na = normalizeForMatch($a);
    $nb = normalizeForMatch($b);
    if ($na === $nb) {
        return false;
    }
    // Same branding, different federal subject in title (titles use "е" or "ё"; case varies)
    $volMed = '/волонт[её]ры?-медики\s*\|\s*(.+)$/u';
    if (preg_match($volMed, $na, $ma) && preg_match($volMed, $nb, $mb)) {
        return normalizeForMatch(trim($ma[1])) !== normalizeForMatch(trim($mb[1]));
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

function shouldExclude(array $p): bool
{
    $ta = $p['title_a'] ?? '';
    $tb = $p['title_b'] ?? '';
    $sim = (float) ($p['similarity_pct'] ?? 0);

    if (normalizeForMatch($ta) === normalizeForMatch($tb)) {
        return false;
    }

    if (isMedicalContext($ta) && isMedicalContext($tb)) {
        // Different cities / subjects with the same "№3" are still different legal entities.
        if (normalizeForMatch($ta) !== normalizeForMatch($tb)) {
            return true;
        }
    }

    if (templateDifferentRegion($ta, $tb)) {
        return true;
    }

    $na = normalizeForMatch($ta);
    $nb = normalizeForMatch($tb);
    // "Благотворительный склад" vs "благотворительный фонд" — разные формы, не мержим по fuzzy
    if ((preg_match('/\bсклад\b/u', $na) && preg_match('/\bфонд\b/u', $nb))
        || (preg_match('/\bфонд\b/u', $na) && preg_match('/\bсклад\b/u', $nb))) {
        return true;
    }

    // ANO / CSO / similar: different trade name in quotes (Ника vs Вера, Синара vs Манара)
    $n = $na;
    if (preg_match('/автономная некоммерческая|центр социального обслуживания|благотворительный фонд/u', $n)) {
        if (quotedSignatureDiffers($ta, $tb)) {
            return true;
        }
    }

    // ТОС "Центральный" vs "Центральный-8"
    if (preg_match('/^тос\s/u', $n) && quotedSignatureDiffers($ta, $tb)) {
        return true;
    }

    return false;
}

$merge = [];
$excluded = [];
foreach ($pairs as $p) {
    if (shouldExclude($p)) {
        $excluded[] = $p;
    } else {
        $merge[] = $p;
    }
}

// De-duplicate merge targets: same without_legal_id should merge once to same with_legal_id (keep highest similarity)
$byDup = [];
foreach ($merge as $p) {
    $k = $p['without_legal_id'].'|'.$p['with_legal_id'];
    if (! isset($byDup[$k]) || $p['similarity_pct'] > $byDup[$k]['similarity_pct']) {
        $byDup[$k] = $p;
    }
}
$mergeUnique = array_values($byDup);
usort($mergeUnique, fn ($a, $b) => $b['similarity_pct'] <=> $a['similarity_pct']);

echo 'EXCLUDED: '.count($excluded)." pairs\n";
echo 'TO_MERGE (unique dup→canonical): '.count($mergeUnique)." pairs\n\n";

foreach ($mergeUnique as $p) {
    echo sprintf(
        "%.1f%% | MERGE dup %s → canonical %s | INN %s OGRN %s\n  dup:  %s\n  can:  %s\n\n",
        $p['similarity_pct'],
        $p['without_legal_id'],
        $p['with_legal_id'],
        $p['with_inn'] ?? '∅',
        $p['with_ogrn'] ?? '∅',
        mb_substr($p['title_a'], 0, 140),
        mb_substr($p['title_b'], 0, 140)
    );
}
