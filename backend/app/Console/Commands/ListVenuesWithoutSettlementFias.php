<?php

namespace App\Console\Commands;

use App\Models\Venue;
use Illuminate\Console\Command;

/**
 * List venues that need separate processing: no fias_id at all, or fias_level is not
 * settlement/city (4=город, 6=населённый пункт). Such venues may need re-enrichment
 * to get settlement-level fias_id or manual assignment.
 */
class ListVenuesWithoutSettlementFias extends Command
{
    protected $signature = 'venues:list-without-settlement-fias
                            {--export= : Export IDs to file (one UUID per line)}';

    protected $description = 'List venues without fias_id or with fias_id not at settlement level (for separate processing)';

    /** FIAS levels: 4 = city, 6 = settlement (населённый пункт). */
    private const SETTLEMENT_LEVELS = ['4', '6'];

    public function handle(): int
    {
        $query = Venue::query()
            ->where(function ($q) {
                $q->where(function ($q2) {
                    $q2->whereNull('fias_id')->orWhere('fias_id', '');
                })->orWhere(function ($q2) {
                    $q2->whereNotNull('fias_level')
                        ->whereNotIn('fias_level', self::SETTLEMENT_LEVELS);
                });
            });

        $venues = $query->orderBy('id')->get();

        if ($venues->isEmpty()) {
            $this->info('No venues without settlement-level fias_id.');

            return self::SUCCESS;
        }

        $this->info('Venues without fias_id at settlement level (total: '.$venues->count().')');
        $this->newLine();

        $rows = $venues->map(fn (Venue $v) => [
            $v->id,
            $v->fias_id ?? '—',
            $v->fias_level ?? '—',
            mb_substr($v->address_raw ?? '', 0, 50),
        ])->all();

        $this->table(['id', 'fias_id', 'fias_level', 'address_raw'], $rows);

        $exportPath = $this->option('export');
        if ($exportPath !== null && $exportPath !== '') {
            $content = $venues->pluck('id')->implode("\n");
            file_put_contents($exportPath, $content);
            $this->info('Exported '.$venues->count().' IDs to '.$exportPath);
        }

        return self::SUCCESS;
    }
}
