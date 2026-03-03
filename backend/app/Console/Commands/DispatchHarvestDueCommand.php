<?php

namespace App\Console\Commands;

use App\Models\Source;
use Illuminate\Console\Command;
use Illuminate\Support\Facades\Http;

/**
 * Fetch sources due for crawling and dispatch them to Harvester via POST /harvest/run.
 *
 * Schedule in app/Console/Kernel.php, e.g. daily:
 *   $schedule->command('harvest:dispatch-due')->daily()->at('02:00');
 *
 * Requires HARVESTER_URL and HARVESTER_API_TOKEN in .env (token must match
 * Harvester's HARVESTER_API_TOKEN / API auth).
 */
class DispatchHarvestDueCommand extends Command
{
    protected $signature = 'harvest:dispatch-due
                            {--limit=100 : Max number of due sources to send (max 500)}
                            {--dry-run : Only list due sources, do not call Harvester}';

    protected $description = 'Dispatch due sources to Harvester (POST /harvest/run)';

    public function handle(): int
    {
        $limit = min((int) $this->option('limit'), 500);
        $dryRun = (bool) $this->option('dry-run');

        $sources = Source::query()
            ->due()
            ->limit($limit)
            ->get(['id', 'base_url', 'organizer_id']);

        if ($sources->isEmpty()) {
            $this->info('No due sources.');

            return self::SUCCESS;
        }

        $payload = [
            'sources' => $sources->map(fn ($s) => [
                'url' => $s->base_url,
                'source_id' => $s->id,
                'source_item_id' => $s->base_url,
                'existing_entity_id' => $s->organizer_id,
            ])->values()->all(),
            'multi_page' => true,
            'enrich_geo' => true,
            'send_to_core' => true,
        ];

        $this->info(sprintf('Due sources: %d (limit=%d)', $sources->count(), $limit));

        if ($dryRun) {
            $this->line('Dry run — would POST to Harvester:');
            foreach ($sources->take(5) as $s) {
                $this->line('  '.$s->base_url.' ('.$s->id.')');
            }
            if ($sources->count() > 5) {
                $this->line('  ... and '.($sources->count() - 5).' more');
            }

            return self::SUCCESS;
        }

        $url = rtrim(config('services.harvester.url'), '/').'/harvest/run';
        $token = config('services.harvester.api_token');

        if (! $url || ! $token) {
            $this->error('HARVESTER_URL and HARVESTER_API_TOKEN must be set in .env');

            return self::FAILURE;
        }

        $response = Http::withHeaders([
            'Authorization' => 'Bearer '.$token,
            'Accept' => 'application/json',
            'Content-Type' => 'application/json',
        ])
            ->timeout(30)
            ->post($url, $payload);

        if (! $response->successful()) {
            $this->error('Harvester responded with '.$response->status().': '.$response->body());

            return self::FAILURE;
        }

        $body = $response->json();
        $this->info('Dispatched: '.($body['message'] ?? 'ok').' (group_id: '.($body['group_id'] ?? 'n/a').')');

        return self::SUCCESS;
    }
}
