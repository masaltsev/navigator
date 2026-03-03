<?php

namespace App\Console\Commands;

use App\Models\Organization;
use App\Services\Dadata\DadataClient;
use App\Services\VenueAddressEnricher\VenueAddressEnricher;
use Illuminate\Console\Command;
use Illuminate\Support\Facades\DB;

/**
 * Enrich organizations via DaData findById/party (suggestion by INN/OGRN).
 * Updates: missing INN/OGRN, organizer contacts (only if empty), related venues (with --force).
 */
class EnrichOrganizationsFromDadata extends Command
{
    protected $signature = 'organizations:enrich-from-dadata
                            {--limit=0 : Max organizations per run (0 = no limit)}
                            {--venue-ids= : Comma-separated venue UUIDs; only process orgs that have at least one of these venues}
                            {--force-venues : Overwrite venue address/fias/region from DaData}
                            {--dry-run : Do not save, only show planned updates}';

    protected $description = 'Enrich organizations via DaData findById/party (INN/OGRN); fill missing INN/OGRN, organizer contacts, venue data';

    private const DELAY_MS = 250;

    public function handle(): int
    {
        if (! config('services.dadata.api_key')) {
            $this->error('DADATA_API_KEY is not set in .env');

            return self::FAILURE;
        }

        $limit = (int) $this->option('limit');
        $venueIdsOption = $this->option('venue-ids');
        $forceVenues = (bool) $this->option('force-venues');
        $dryRun = (bool) $this->option('dry-run');

        $query = Organization::query()
            ->where('status', 'approved')
            ->where(function ($q) {
                $q->whereNotNull('inn')->where('inn', '!=', '')
                    ->orWhereNotNull('ogrn')->where('ogrn', '!=', '');
            })
            ->with(['organizer', 'venues'])
            ->orderBy('id');

        if ($venueIdsOption !== null && $venueIdsOption !== '') {
            $venueIds = array_filter(array_map('trim', explode(',', $venueIdsOption)));
            if ($venueIds !== []) {
                $query->whereHas('venues', function ($q) use ($venueIds) {
                    $q->whereIn('venues.id', $venueIds);
                });
            }
        }

        if ($limit > 0) {
            $query->limit($limit);
        }

        $organizations = $query->get();
        if ($organizations->isEmpty()) {
            $this->info('No organizations with INN or OGRN to process.');

            return self::SUCCESS;
        }

        $this->info('Processing '.$organizations->count().' organization(s). force-venues='.($forceVenues ? 'yes' : 'no').', dry-run='.($dryRun ? 'yes' : 'no'));

        $client = DadataClient::fromConfig();
        $venueEnricher = new VenueAddressEnricher($client);

        $updatedOrgs = 0;
        $updatedContacts = 0;
        $updatedVenues = 0;

        foreach ($organizations as $org) {
            $innOrOgrn = trim($org->inn ?? '') !== '' ? $org->inn : $org->ogrn;
            if ($innOrOgrn === '') {
                continue;
            }

            usleep(self::DELAY_MS * 1000);
            $data = $client->findPartyById($innOrOgrn);
            if (! $data) {
                if ($this->output->isVerbose()) {
                    $this->line("  [{$org->id}] findById/party: no data for {$innOrOgrn}");
                }

                continue;
            }

            $changed = false;

            // Update organization: missing INN/OGRN (only if not already used by another org)
            $newInn = isset($data['inn']) && is_string($data['inn']) && $data['inn'] !== '' ? trim($data['inn']) : null;
            $newOgrn = isset($data['ogrn']) && is_string($data['ogrn']) && $data['ogrn'] !== '' ? trim($data['ogrn']) : null;
            if ($newInn !== null && (trim($org->inn ?? '') === '')) {
                $innTaken = Organization::query()->where('inn', $newInn)->where('id', '!=', $org->id)->exists();
                if (! $innTaken && ! $dryRun) {
                    $org->inn = $newInn;
                }
                if (! $innTaken) {
                    $changed = true;
                }
            }
            if ($newOgrn !== null && (trim($org->ogrn ?? '') === '')) {
                $ogrnTaken = Organization::query()->where('ogrn', $newOgrn)->where('id', '!=', $org->id)->exists();
                if (! $ogrnTaken && ! $dryRun) {
                    $org->ogrn = $newOgrn;
                }
                if (! $ogrnTaken) {
                    $changed = true;
                }
            }
            if ($changed && ! $dryRun) {
                $org->save();
                $updatedOrgs++;
            }

            // Update organizer: contacts only if empty (no --force for contacts)
            $organizer = $org->organizer;
            if ($organizer) {
                $phones = $this->extractPhones($data);
                $emails = $this->extractEmails($data);
                $updateContacts = false;
                if ($phones !== [] && ($organizer->contact_phones === null || $organizer->contact_phones === [])) {
                    if (! $dryRun) {
                        $organizer->contact_phones = $phones;
                    }
                    $updateContacts = true;
                }
                if ($emails !== [] && ($organizer->contact_emails === null || $organizer->contact_emails === [])) {
                    if (! $dryRun) {
                        $organizer->contact_emails = $emails;
                    }
                    $updateContacts = true;
                }
                if ($updateContacts && ! $dryRun) {
                    $organizer->save();
                    $updatedContacts++;
                }
            }

            // Venues: with --force-venues, set address from party and re-enrich
            if ($forceVenues && $org->venues->isNotEmpty()) {
                $partyAddress = $this->extractPartyAddress($data);
                foreach ($org->venues as $venue) {
                    if ($partyAddress !== null && $partyAddress !== '') {
                        if (! $dryRun) {
                            $venue->address_raw = $partyAddress;
                            $venue->save();
                        }
                    }
                    usleep((int) (self::DELAY_MS * 1000));
                    $result = $venueEnricher->enrichByAddress($venue);
                    if ($result->isSuccess() && ! $dryRun) {
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
                        $updatedVenues++;
                    }
                }
            }
        }

        $this->newLine();
        $this->info("Done. Organizations updated: {$updatedOrgs}, organizer contacts: {$updatedContacts}, venues: {$updatedVenues}.");

        return self::SUCCESS;
    }

    /**
     * @param  array<string, mixed>  $data
     * @return array<int, string>
     */
    private function extractPhones(array $data): array
    {
        $phones = $data['phones'] ?? [];
        if (! is_array($phones)) {
            return [];
        }
        $out = [];
        foreach ($phones as $p) {
            $value = $p['value'] ?? $p['data']['source'] ?? null;
            if (is_string($value) && trim($value) !== '') {
                $out[] = trim($value);
            }
        }

        return $out;
    }

    /**
     * @param  array<string, mixed>  $data
     * @return array<int, string>
     */
    private function extractEmails(array $data): array
    {
        $emails = $data['emails'] ?? [];
        if (! is_array($emails)) {
            return [];
        }
        $out = [];
        foreach ($emails as $e) {
            $value = $e['value'] ?? $e['data']['source'] ?? null;
            if (is_string($value) && trim($value) !== '') {
                $out[] = trim($value);
            }
        }

        return $out;
    }

    /**
     * @param  array<string, mixed>  $data
     */
    private function extractPartyAddress(array $data): ?string
    {
        $addr = $data['address'] ?? null;
        if (! is_array($addr)) {
            return null;
        }
        $value = $addr['value'] ?? $addr['unrestricted_value'] ?? null;

        return is_string($value) && trim($value) !== '' ? trim($value) : null;
    }
}
