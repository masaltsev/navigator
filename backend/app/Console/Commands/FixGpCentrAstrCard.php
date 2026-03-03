<?php

namespace App\Console\Commands;

use App\Models\Organization;
use App\Models\Source;
use Illuminate\Console\Command;
use Illuminate\Support\Str;

/**
 * One-off: restore organization card that had title "27.01.2026" (gp-centr.astr.socinfo.ru).
 * Use on prod after restoring DB from dev — IDs are identical.
 *
 * 1. Updates organization title/short_title to a sensible name from description.
 * 2. Creates org_website source for that organizer if missing.
 */
class FixGpCentrAstrCard extends Command
{
    protected $signature = 'one-off:fix-gp-centr-astr-card
                            {--dry-run : Do not save, only show what would be done}';

    protected $description = 'One-off: fix organization 27.01.2026 (Geriatic centre, Kirovsky) title and ensure source exists';

    private const ORG_ID = '019c97b9-fec7-7128-b5a2-58a3b60c2387';
    private const ORGANIZER_ID = '019c97b9-fecb-7231-8a9d-5651c36c3654';
    private const BASE_URL = 'https://gp-centr.astr.socinfo.ru/';
    private const NEW_TITLE = 'Гериатрический центр (пос. Кировский, Астраханская обл.)';
    private const NEW_SHORT_TITLE = 'Гериатрический центр, пос. Кировский';

    public function handle(): int
    {
        $dryRun = (bool) $this->option('dry-run');

        $org = Organization::find(self::ORG_ID);
        if (! $org) {
            $this->warn('Organization '.self::ORG_ID.' not found. Nothing to do.');

            return self::SUCCESS;
        }

        $done = false;

        if ($org->title === '27.01.2026') {
            $this->line('Organization current title: 27.01.2026');
            if (! $dryRun) {
                $org->title = self::NEW_TITLE;
                $org->short_title = self::NEW_SHORT_TITLE;
                $org->save();
            }
            $this->info('  → '.($dryRun ? 'Would set' : 'Set').' title: '.self::NEW_TITLE);
            $done = true;
        } else {
            $this->line('Organization title already set: '.$org->title);
        }

        $sourceExists = Source::where('organizer_id', self::ORGANIZER_ID)
            ->where('base_url', self::BASE_URL)
            ->exists();

        if (! $sourceExists) {
            $hostname = 'gp-centr.astr.socinfo.ru';
            if (! $dryRun) {
                Source::create([
                    'id' => (string) Str::uuid(),
                    'name' => $hostname,
                    'kind' => 'org_website',
                    'base_url' => self::BASE_URL,
                    'entry_points' => [],
                    'is_active' => true,
                    'last_status' => 'pending',
                    'organizer_id' => self::ORGANIZER_ID,
                    'crawl_period_days' => 30,
                ]);
            }
            $this->info('  → '.($dryRun ? 'Would create' : 'Created').' source '.$hostname.' for organizer '.self::ORGANIZER_ID);
            $done = true;
        } else {
            $this->line('Source for '.self::BASE_URL.' already exists for this organizer.');
        }

        if (! $done) {
            $this->info('Nothing to change.');
        } elseif ($dryRun) {
            $this->newLine();
            $this->comment('Run without --dry-run to apply.');
        }

        return self::SUCCESS;
    }
}
