<?php

namespace App\Services\WpMigration;

use Illuminate\Support\Facades\DB;

/**
 * Repository for extracting and aggregating WordPress/HivePress listing data.
 *
 * Handles the EAV (Entity-Attribute-Value) structure of WordPress postmeta,
 * aggregating metadata into flat structures using SQL aggregation.
 */
class WpListingRepository
{
    /**
     * WordPress database connection name.
     */
    private const WP_CONNECTION = 'mysql_wp';

    /**
     * Custom post type for HivePress listings.
     */
    private const POST_TYPE = 'hp_listing';

    /**
     * Fetch listings in chunks with aggregated metadata.
     */
    public function chunkListings(int $chunkSize, callable $callback): void
    {
        $prefix = DB::connection(self::WP_CONNECTION)->getTablePrefix();
        $postsTable = $prefix.'posts';
        $postmetaTable = $prefix.'postmeta';

        // Use raw SQL to avoid Laravel's alias prefixing issues
        $sql = "
            SELECT 
                p.ID as post_id,
                p.post_title,
                p.post_content,
                p.post_date,
                p.post_modified,
                MAX(CASE WHEN pm.meta_key = 'hp_inn' THEN pm.meta_value END) as hp_inn,
                MAX(CASE WHEN pm.meta_key = 'hp_ogrn' THEN pm.meta_value END) as hp_ogrn,
                MAX(CASE WHEN pm.meta_key = 'hp_phone' THEN pm.meta_value END) as hp_phone,
                MAX(CASE WHEN pm.meta_key = 'hp_email' THEN pm.meta_value END) as hp_email,
                MAX(CASE WHEN pm.meta_key = 'hp_site' THEN pm.meta_value END) as hp_site,
                MAX(CASE WHEN pm.meta_key = 'hp_location' THEN pm.meta_value END) as hp_location,
                MAX(CASE WHEN pm.meta_key = 'hp_town' THEN pm.meta_value END) as hp_town,
                MAX(CASE WHEN pm.meta_key = 'hp_region' THEN pm.meta_value END) as hp_region,
                MAX(CASE WHEN pm.meta_key = 'hp_latitude' THEN pm.meta_value END) as hp_latitude,
                MAX(CASE WHEN pm.meta_key = 'hp_longitude' THEN pm.meta_value END) as hp_longitude,
                MAX(CASE WHEN pm.meta_key = 'hp_ceo' THEN pm.meta_value END) as hp_ceo,
                MAX(CASE WHEN pm.meta_key = 'hp_dobro_ru' THEN pm.meta_value END) as hp_dobro_ru
            FROM {$postsTable} p
            LEFT JOIN {$postmetaTable} pm ON p.ID = pm.post_id
            WHERE p.post_type = ? AND p.post_status = 'publish'
            GROUP BY p.ID, p.post_title, p.post_content, p.post_date, p.post_modified
            ORDER BY p.ID ASC
        ";

        $offset = 0;
        do {
            $results = DB::connection(self::WP_CONNECTION)
                ->select($sql.' LIMIT ? OFFSET ?', [self::POST_TYPE, $chunkSize, $offset]);

            foreach ($results as $listing) {
                $callback($listing);
            }

            $offset += $chunkSize;
        } while (count($results) === $chunkSize);
    }

    /**
     * Fetch listings by post IDs (same structure as chunkListings).
     * Used to re-process failed listings after migration with updated rules.
     *
     * @param  array<int>  $postIds
     * @return array<object>
     */
    public function getListingsByPostIds(array $postIds): array
    {
        if ($postIds === []) {
            return [];
        }

        $prefix = DB::connection(self::WP_CONNECTION)->getTablePrefix();
        $postsTable = $prefix.'posts';
        $postmetaTable = $prefix.'postmeta';

        $placeholders = implode(',', array_fill(0, count($postIds), '?'));
        $sql = "
            SELECT 
                p.ID as post_id,
                p.post_title,
                p.post_content,
                p.post_date,
                p.post_modified,
                MAX(CASE WHEN pm.meta_key = 'hp_inn' THEN pm.meta_value END) as hp_inn,
                MAX(CASE WHEN pm.meta_key = 'hp_ogrn' THEN pm.meta_value END) as hp_ogrn,
                MAX(CASE WHEN pm.meta_key = 'hp_phone' THEN pm.meta_value END) as hp_phone,
                MAX(CASE WHEN pm.meta_key = 'hp_email' THEN pm.meta_value END) as hp_email,
                MAX(CASE WHEN pm.meta_key = 'hp_site' THEN pm.meta_value END) as hp_site,
                MAX(CASE WHEN pm.meta_key = 'hp_location' THEN pm.meta_value END) as hp_location,
                MAX(CASE WHEN pm.meta_key = 'hp_town' THEN pm.meta_value END) as hp_town,
                MAX(CASE WHEN pm.meta_key = 'hp_region' THEN pm.meta_value END) as hp_region,
                MAX(CASE WHEN pm.meta_key = 'hp_latitude' THEN pm.meta_value END) as hp_latitude,
                MAX(CASE WHEN pm.meta_key = 'hp_longitude' THEN pm.meta_value END) as hp_longitude,
                MAX(CASE WHEN pm.meta_key = 'hp_ceo' THEN pm.meta_value END) as hp_ceo,
                MAX(CASE WHEN pm.meta_key = 'hp_dobro_ru' THEN pm.meta_value END) as hp_dobro_ru
            FROM {$postsTable} p
            LEFT JOIN {$postmetaTable} pm ON p.ID = pm.post_id
            WHERE p.post_type = ? AND p.ID IN ({$placeholders})
            GROUP BY p.ID, p.post_title, p.post_content, p.post_date, p.post_modified
            ORDER BY p.ID ASC
        ";

        $bindings = [self::POST_TYPE, ...$postIds];

        return DB::connection(self::WP_CONNECTION)->select($sql, $bindings);
    }

    /**
     * Get taxonomy term IDs for a listing.
     * Uses raw SQL with explicit table prefix to avoid alias/prefix issues.
     *
     * @return array<int>
     */
    public function getTaxonomyTermIds(int $postId, string $taxonomy): array
    {
        $prefix = DB::connection(self::WP_CONNECTION)->getTablePrefix();
        $tr = $prefix.'term_relationships';
        $tt = $prefix.'term_taxonomy';
        $t = $prefix.'terms';

        $rows = DB::connection(self::WP_CONNECTION)->select(
            "SELECT t.term_id FROM {$tr} tr
             INNER JOIN {$tt} tt ON tr.term_taxonomy_id = tt.term_taxonomy_id
             INNER JOIN {$t} t ON tt.term_id = t.term_id
             WHERE tr.object_id = ? AND tt.taxonomy = ?",
            [$postId, $taxonomy]
        );

        return array_map(fn ($r) => (int) $r->term_id, $rows);
    }

    /**
     * Get all taxonomy term IDs for a listing (categories, services, types, ownership).
     *
     * @return array<string, array<int>>
     */
    public function getAllTaxonomiesForListing(int $postId): array
    {
        return [
            'categories' => $this->getTaxonomyTermIds($postId, 'hp_listing_category'),
            'services' => $this->getTaxonomyTermIds($postId, 'hp_listing_service'),
            'types' => $this->getTaxonomyTermIds($postId, 'hp_listing_type'),
            'ownership' => $this->getTaxonomyTermIds($postId, 'hp_listing_ownership'),
        ];
    }

    /**
     * Get WordPress posts that should be migrated as articles.
     * Uses raw SQL with explicit table prefix.
     */
    public function chunkArticles(int $chunkSize, callable $callback): void
    {
        $prefix = DB::connection(self::WP_CONNECTION)->getTablePrefix();
        $postsTable = $prefix.'posts';

        $offset = 0;
        do {
            $posts = DB::connection(self::WP_CONNECTION)->select(
                "SELECT * FROM {$postsTable} WHERE post_type = 'post' AND post_status = 'publish' ORDER BY ID ASC LIMIT ? OFFSET ?",
                [$chunkSize, $offset]
            );
            foreach ($posts as $post) {
                $callback($post);
            }
            $offset += $chunkSize;
        } while (count($posts) === $chunkSize);
    }
}
