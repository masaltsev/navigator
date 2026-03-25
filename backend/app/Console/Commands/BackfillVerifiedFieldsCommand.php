<?php

namespace App\Console\Commands;

use App\Models\Organization;
use App\Services\Dadata\DadataClient;
use Illuminate\Console\Command;

/**
 * Backfill verified_fields for existing organizations by validating
 * their INN/OGRN against DaData findById/party.
 *
 * Organizations where DaData confirms the INN get:
 *   verified_fields = {"inn": "dadata", "ogrn": "dadata", "title": "dadata"}
 */
class BackfillVerifiedFieldsCommand extends Command
{
    protected $signature = 'organizations:backfill-verified-fields
                            {--limit=0 : Max organizations per run (0 = all)}
                            {--dry-run : Show what would be updated without saving}';

    protected $description = 'Backfill verified_fields for orgs with INN/OGRN by checking DaData';

    private const DELAY_MS = 100;

    public function handle(): int
    {
        if (! config('services.dadata.api_key')) {
            $this->error('DADATA_API_KEY is not set in .env');

            return self::FAILURE;
        }

        $limit = (int) $this->option('limit');
        $dryRun = (bool) $this->option('dry-run');

        $query = Organization::query()
            ->where('status', 'approved')
            ->where(function ($q) {
                $q->whereNotNull('inn')->where('inn', '!=', '')
                    ->orWhere(function ($q2) {
                        $q2->whereNotNull('ogrn')->where('ogrn', '!=', '');
                    });
            })
            ->where(function ($q) {
                $q->whereNull('verified_fields')
                    ->orWhereRaw("verified_fields = '{}'::jsonb")
                    ->orWhereRaw("verified_fields = 'null'::jsonb");
            })
            ->orderBy('id');

        if ($limit > 0) {
            $query->limit($limit);
        }

        $organizations = $query->get();
        if ($organizations->isEmpty()) {
            $this->info('No organizations need backfilling.');

            return self::SUCCESS;
        }

        $this->info(sprintf(
            'Processing %d organization(s). dry-run=%s',
            $organizations->count(),
            $dryRun ? 'yes' : 'no',
        ));

        $client = DadataClient::fromConfig();
        $verified = 0;
        $notFound = 0;

        $bar = $this->output->createProgressBar($organizations->count());
        $bar->start();

        foreach ($organizations as $org) {
            $innOrOgrn = trim($org->inn ?? '') !== '' ? $org->inn : $org->ogrn;
            if ($innOrOgrn === '' || $innOrOgrn === null) {
                $bar->advance();

                continue;
            }

            usleep(self::DELAY_MS * 1000);
            $data = $client->findPartyById($innOrOgrn);

            if (! $data || empty($data['inn'])) {
                $notFound++;
                $bar->advance();

                continue;
            }

            $dadataInn = $data['inn'] ?? null;
            $dadataOgrn = $data['ogrn'] ?? null;

            $fields = [];
            if ($dadataInn && ($dadataInn === $org->inn || trim($org->inn ?? '') === '')) {
                $fields['inn'] = 'dadata';
            }
            if ($dadataOgrn && ($dadataOgrn === $org->ogrn || trim($org->ogrn ?? '') === '')) {
                $fields['ogrn'] = 'dadata';
            }

            $nameData = $data['name'] ?? [];
            if (is_array($nameData) && (! empty($nameData['full_with_opf']) || ! empty($nameData['short_with_opf']))) {
                $fields['title'] = 'dadata';
                $fields['short_title'] = 'dadata';
            }

            if ($fields === []) {
                $notFound++;
                $bar->advance();

                continue;
            }

            if (! $dryRun) {
                $org->update(['verified_fields' => $fields]);
            }

            $verified++;

            if ($this->output->isVerbose()) {
                $this->newLine();
                $this->line(sprintf(
                    '  [%s] %s → verified: %s',
                    $org->id,
                    mb_substr($org->title, 0, 50),
                    implode(', ', array_keys($fields)),
                ));
            }

            $bar->advance();
        }

        $bar->finish();
        $this->newLine(2);
        $this->info(sprintf(
            'Done. Verified: %d, not found in DaData: %d.',
            $verified,
            $notFound,
        ));

        return self::SUCCESS;
    }
}
