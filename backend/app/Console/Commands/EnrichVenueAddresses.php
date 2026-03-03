<?php

namespace App\Console\Commands;

use App\Models\Venue;
use App\Services\Dadata\DadataClient;
use App\Services\VenueAddressEnricher\EnrichmentResult;
use App\Services\VenueAddressEnricher\VenueAddressEnricher;
use Illuminate\Console\Command;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;

/**
 * Enrich venues with fias_id, kladr_id, region_iso, coordinates via DaData API.
 *
 * @see docs/address_enrichment_via_dadata.md
 */
class EnrichVenueAddresses extends Command
{
    protected $signature = 'venues:enrich-addresses
                            {--limit=100 : Max number of venues per run}
                            {--force : Overwrite fias_id even if already set}
                            {--by-geo : Enrich by coordinates (venues without address_raw, with coordinates)}
                            {--use-clean-only : Use only Clean API (no suggest); use when suggest quota is exhausted}
                            {--new-regions-only : Only enrich venues with region_iso = null (LNR, DNR, Kherson, Zaporozhye)}
                            {--dry-run : Do not save to DB, only log planned updates}';

    protected $description = 'Enrich venue addresses via DaData (fias_id, kladr_id, region_iso, coordinates)';

    private int $processed = 0;

    private int $updated = 0;

    private int $notFound = 0;

    private int $errors = 0;

    private const DELAY_MS = 200;

    /** FIAS levels 4 (город), 6 (населённый пункт). With --use-clean-only and no --force we process only venues not at this level. */
    private const SETTLEMENT_LEVELS = ['4', '6'];

    public function handle(): int
    {
        if (config('services.dadata.api_key') === '' || config('services.dadata.api_key') === null) {
            $this->error('DADATA_API_KEY is not set in .env');

            return self::FAILURE;
        }

        $limit = (int) $this->option('limit');
        $force = (bool) $this->option('force');
        $byGeo = (bool) $this->option('by-geo');
        $useCleanOnly = (bool) $this->option('use-clean-only');
        $newRegionsOnly = (bool) $this->option('new-regions-only');
        $dryRun = (bool) $this->option('dry-run');

        $query = Venue::query()->orderBy('id');

        // Filter for new regions only (LNR, DNR, Kherson, Zaporozhye) if requested
        if ($newRegionsOnly) {
            $query->whereNull('region_iso');
        }

        if ($byGeo) {
            $query->where(function ($q) {
                $q->whereNull('address_raw')->orWhere('address_raw', '');
            })->whereNotNull('coordinates')
                ->where(function ($q) {
                    $this->whereVenueIncomplete($q);
                });
        } else {
            $query->whereNotNull('address_raw')->where('address_raw', '!=', '');
            if (! $force) {
                $query->where(function ($q) {
                    $this->whereVenueIncomplete($q);
                });
            }
        }

        $venues = $query->limit($limit)->get();

        if ($venues->isEmpty()) {
            $this->info('No venues to process.');

            return self::SUCCESS;
        }

        if ($useCleanOnly && ! $byGeo) {
            if (config('services.dadata.secret_key') === '' || config('services.dadata.secret_key') === null) {
                $this->error('DADATA_SECRET_KEY is required for --use-clean-only (Clean API).');

                return self::FAILURE;
            }
            $this->info('Mode: Clean API only (no suggest).');
            if (! $force) {
                $this->info('Target: only venues without fias_id or with fias_level not at settlement (4/6).');
            }
        }

        $this->info('Processing '.$venues->count().' venue(s). Dry-run: '.($dryRun ? 'yes' : 'no'));

        $client = DadataClient::fromConfig();
        $enricher = new VenueAddressEnricher($client);

        foreach ($venues as $venue) {
            $this->processVenue($venue, $enricher, $byGeo, $useCleanOnly, $dryRun);
            usleep(self::DELAY_MS * 1000);
        }

        $this->newLine();
        $this->info('Done. Processed: '.$this->processed.', updated: '.$this->updated.', not_found: '.$this->notFound.', errors: '.$this->errors);

        return self::SUCCESS;
    }

    private function processVenue(Venue $venue, VenueAddressEnricher $enricher, bool $byGeo, bool $useCleanOnly, bool $dryRun): void
    {
        $result = null;

        try {
            if ($byGeo) {
                $result = $enricher->enrichByCoordinates($venue);
            } elseif ($useCleanOnly) {
                $result = $enricher->enrichByAddressCleanOnly($venue);
            } else {
                $result = $enricher->enrichByAddress($venue);
            }

            if (! $byGeo && ! $useCleanOnly && ! $result->isSuccess() && $this->venueHasCoordinates($venue)) {
                usleep(self::DELAY_MS * 1000);
                $fallback = $enricher->enrichByCoordinates($venue);
                if ($fallback->isSuccess()) {
                    $result = $fallback;
                    if ($this->output->isVerbose()) {
                        $this->line("  [{$venue->id}] fallback to by-geo succeeded");
                    }
                }
            }
        } catch (\Throwable $e) {
            $this->errors++;
            Log::warning('Venue enrich failed', ['venue_id' => $venue->id, 'error' => $e->getMessage()]);
            $this->warn("  [{$venue->id}] Error: ".$e->getMessage());

            return;
        }

        $this->processed++;

        if ($result->status === EnrichmentResult::STATUS_NOT_FOUND) {
            $this->notFound++;
            if ($this->output->isVerbose()) {
                $this->line("  [{$venue->id}] not_found");
            }

            return;
        }

        if ($result->status === EnrichmentResult::STATUS_ERROR) {
            $this->errors++;
            $this->warn("  [{$venue->id}] ".$result->errorMessage);

            return;
        }

        if ($dryRun) {
            $regionInfo = $result->regionIso !== null ? "region_iso={$result->regionIso}" : 'region_code='.($result->regionCode ?? 'null');
            $this->line("  [{$venue->id}] would set fias_id={$result->fiasId}, city_fias_id=".($result->cityFiasId ?? 'null').', fias_level='.($result->fiasLevel ?? 'null').', kladr_id='.($result->kladrId ?? 'null').', '.$regionInfo.($result->lat !== null ? ", lat={$result->lat}, lon={$result->lon}" : ''));
            $this->updated++;

            return;
        }

        $venue->fias_id = $result->fiasId;
        $venue->fias_level = $result->fiasLevel;
        $venue->city_fias_id = $result->cityFiasId;
        $venue->kladr_id = $result->kladrId;
        $venue->region_iso = $result->regionIso;
        $venue->region_code = $result->regionCode;
        $venue->save();

        if ($result->lat !== null && $result->lon !== null) {
            DB::update(
                'UPDATE venues SET coordinates = ST_SetSRID(ST_MakePoint(?, ?), 4326) WHERE id = ?',
                [$result->lon, $result->lat, $venue->id]
            );
        }

        $this->updated++;
        if ($this->output->isVerbose()) {
            $this->info("  [{$venue->id}] updated fias_id={$result->fiasId}");
        }
    }

    private function venueHasCoordinates(Venue $venue): bool
    {
        $row = DB::selectOne(
            'SELECT 1 FROM venues WHERE id = ? AND coordinates IS NOT NULL',
            [$venue->id]
        );

        return $row !== null;
    }

    /**
     * Restrict to venues missing at least one of: fias_id, fias_level, city_fias_id, region_iso, coordinates.
     * Used when not --force so we skip venues that are already complete.
     */
    private function whereVenueIncomplete($query): void
    {
        $query->where(function ($q) {
            $q->whereNull('fias_id')->orWhere('fias_id', '')
                ->orWhereNull('fias_level')->orWhere('fias_level', '')
                ->orWhereNull('city_fias_id')->orWhere('city_fias_id', '')
                ->orWhereNull('region_iso')->orWhere('region_iso', '')
                ->orWhereNull('coordinates');
        });
    }
}
