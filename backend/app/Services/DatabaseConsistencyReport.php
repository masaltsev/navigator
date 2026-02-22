<?php

namespace App\Services;

use Illuminate\Support\Facades\DB;

/**
 * Reports consistency of Organization -> Organizer -> Venue + org_website Source.
 *
 * Ideal: 1 organization -> 1 organizer -> exactly 1 venue and exactly 1 org_website source.
 */
class DatabaseConsistencyReport
{
    private const ORGANIZER_TYPE = 'Organization';

    /**
     * Run the report for approved organizations.
     *
     * @return array{total: int, ideal: int, partial: int, breakdown: array<string, int>}
     */
    public function run(): array
    {
        $rows = $this->fetchOrganizationStats();

        $total = count($rows);
        $ideal = 0;
        $breakdown = [
            'no_organizer' => 0,
            'organizer_but_no_venue' => 0,
            'organizer_but_multiple_venues' => 0,
            'organizer_but_no_org_website_source' => 0,
            'organizer_but_multiple_org_website_sources' => 0,
            'ideal' => 0,
        ];

        foreach ($rows as $row) {
            $hasOrganizer = (int) $row->organizer_count >= 1;
            $venueCount = (int) $row->venue_count;
            $orgWebsiteCount = (int) $row->org_website_source_count;

            if (! $hasOrganizer) {
                $breakdown['no_organizer']++;

                continue;
            }
            if ($venueCount === 0) {
                $breakdown['organizer_but_no_venue']++;

                continue;
            }
            if ($venueCount > 1) {
                $breakdown['organizer_but_multiple_venues']++;

                continue;
            }
            if ($orgWebsiteCount === 0) {
                $breakdown['organizer_but_no_org_website_source']++;

                continue;
            }
            if ($orgWebsiteCount > 1) {
                $breakdown['organizer_but_multiple_org_website_sources']++;

                continue;
            }
            // 1 organizer, 1 venue, 1 org_website source
            $breakdown['ideal']++;
            $ideal++;
        }

        $partial = $total - $ideal;

        return [
            'total' => $total,
            'ideal' => $ideal,
            'partial' => $partial,
            'breakdown' => $breakdown,
        ];
    }

    /**
     * Fetch per-organization stats: organizer count, venue count, org_website source count.
     *
     * @return array<int, object{organization_id: string, organizer_count: string, venue_count: string, org_website_source_count: string}>
     */
    private function fetchOrganizationStats(): array
    {
        $sql = "
            SELECT
                o.id AS organization_id,
                COALESCE(org_cnt.cnt, 0) AS organizer_count,
                COALESCE(venue_cnt.cnt, 0) AS venue_count,
                COALESCE(src_cnt.cnt, 0) AS org_website_source_count
            FROM organizations o
            LEFT JOIN (
                SELECT organizable_id AS org_id, COUNT(*) AS cnt
                FROM organizers
                WHERE organizable_type = ?
                GROUP BY organizable_id
            ) org_cnt ON org_cnt.org_id = o.id
            LEFT JOIN (
                SELECT organization_id, COUNT(*) AS cnt
                FROM organization_venues
                GROUP BY organization_id
            ) venue_cnt ON venue_cnt.organization_id = o.id
            LEFT JOIN (
                SELECT o2.organizable_id AS org_id, COUNT(s.id) AS cnt
                FROM organizers o2
                JOIN sources s ON s.organizer_id = o2.id AND s.kind = 'org_website'
                WHERE o2.organizable_type = ?
                GROUP BY o2.organizable_id
            ) src_cnt ON src_cnt.org_id = o.id
            WHERE o.status = 'approved'
              AND o.deleted_at IS NULL
        ";

        return DB::select($sql, [self::ORGANIZER_TYPE, self::ORGANIZER_TYPE]);
    }
}
