<?php

namespace App\Services\Import;

use App\Models\Article;
use App\Models\Event;
use App\Models\Organization;
use App\Models\Organizer;
use App\Models\Source;
use App\Models\SuggestedTaxonomyItem;
use Illuminate\Support\Facades\DB;

class OrganizationDuplicateMergeService
{
    /**
     * Merge a duplicate organization into the canonical record: fill gaps on the canonical side,
     * union pivot dictionaries, reassign FKs, move sources, then soft-delete the duplicate.
     */
    public function mergeDuplicateIntoCanonical(Organization $canonical, Organization $duplicate): void
    {
        if ($canonical->is($duplicate)) {
            return;
        }

        DB::transaction(function () use ($canonical, $duplicate) {
            $canonical->refresh();
            $duplicate->refresh();

            $this->mergeScalarAttributes($canonical, $duplicate);
            $canonical->save();

            $this->mergePivotRelations($canonical, $duplicate);
            $this->reassignDependentRows($canonical, $duplicate);
            $this->moveSourcesAndUsers($canonical, $duplicate);

            $dupOrganizer = $this->findOrganizerForOrganization($duplicate);
            $duplicate->delete();
            if ($dupOrganizer) {
                $dupOrganizer->delete();
            }
        });
    }

    private function mergeScalarAttributes(Organization $canonical, Organization $duplicate): void
    {
        if ($this->isEmptyString($canonical->description) && ! $this->isEmptyString($duplicate->description)) {
            $canonical->description = $duplicate->description;
        }

        if ($this->isEmptyString($canonical->short_title) && ! $this->isEmptyString($duplicate->short_title)) {
            $canonical->short_title = $duplicate->short_title;
        }

        if ($this->isEmptyString($canonical->source_reference) && ! $this->isEmptyString($duplicate->source_reference)) {
            $canonical->source_reference = $duplicate->source_reference;
        }

        $canonical->site_urls = $this->mergeStringLists($canonical->site_urls, $duplicate->site_urls);
        $canonical->target_audience = $this->mergeStringLists($canonical->target_audience, $duplicate->target_audience);

        if ($canonical->vk_group_id === null && $duplicate->vk_group_id !== null) {
            $canonical->vk_group_id = $duplicate->vk_group_id;
        }
        if ($canonical->ok_group_id === null && $duplicate->ok_group_id !== null) {
            $canonical->ok_group_id = $duplicate->ok_group_id;
        }

        if ($canonical->ownership_type_id === null && $duplicate->ownership_type_id !== null) {
            $canonical->ownership_type_id = $duplicate->ownership_type_id;
        }
        if ($canonical->coverage_level_id === null && $duplicate->coverage_level_id !== null) {
            $canonical->coverage_level_id = $duplicate->coverage_level_id;
        }

        if (! $canonical->works_with_elderly && $duplicate->works_with_elderly) {
            $canonical->works_with_elderly = true;
        }
    }

    private function mergePivotRelations(Organization $canonical, Organization $duplicate): void
    {
        $canonical->organizationTypes()->syncWithoutDetaching(
            $duplicate->organizationTypes()->pluck('organization_types.id')->all()
        );
        $canonical->thematicCategories()->syncWithoutDetaching(
            $duplicate->thematicCategories()->pluck('thematic_categories.id')->all()
        );
        $canonical->specialistProfiles()->syncWithoutDetaching(
            $duplicate->specialistProfiles()->pluck('specialist_profiles.id')->all()
        );
        $canonical->services()->syncWithoutDetaching(
            $duplicate->services()->pluck('services.id')->all()
        );

        foreach ($duplicate->venues as $venue) {
            $pivot = $venue->pivot;
            $canonical->venues()->syncWithoutDetaching([
                $venue->id => [
                    'is_headquarters' => (bool) ($pivot->is_headquarters ?? false),
                ],
            ]);
        }
    }

    private function reassignDependentRows(Organization $canonical, Organization $duplicate): void
    {
        Event::query()->where('organization_id', $duplicate->id)->update(['organization_id' => $canonical->id]);
        Article::query()->where('organization_id', $duplicate->id)->update(['organization_id' => $canonical->id]);
        SuggestedTaxonomyItem::query()->where('organization_id', $duplicate->id)->update(['organization_id' => $canonical->id]);
    }

    private function moveSourcesAndUsers(Organization $canonical, Organization $duplicate): void
    {
        $canonOrg = $this->findOrganizerForOrganization($canonical);
        $dupOrg = $this->findOrganizerForOrganization($duplicate);

        if (! $canonOrg || ! $dupOrg) {
            return;
        }

        foreach (Source::query()->where('organizer_id', $dupOrg->id)->whereNull('deleted_at')->get() as $source) {
            $conflict = Source::query()
                ->where('organizer_id', $canonOrg->id)
                ->whereNull('deleted_at')
                ->where('base_url', $source->base_url)
                ->exists();

            if ($conflict) {
                $source->delete();
            } else {
                $source->organizer_id = $canonOrg->id;
                $source->save();
            }
        }

        $dupUserLinks = DB::table('user_organizer')->where('organizer_id', $dupOrg->id)->get();
        foreach ($dupUserLinks as $link) {
            $already = DB::table('user_organizer')
                ->where('organizer_id', $canonOrg->id)
                ->where('user_id', $link->user_id)
                ->exists();

            if ($already) {
                DB::table('user_organizer')
                    ->where('organizer_id', $dupOrg->id)
                    ->where('user_id', $link->user_id)
                    ->delete();
            } else {
                DB::table('user_organizer')
                    ->where('organizer_id', $dupOrg->id)
                    ->where('user_id', $link->user_id)
                    ->update(['organizer_id' => $canonOrg->id]);
            }
        }
    }

    private function findOrganizerForOrganization(Organization $organization): ?Organizer
    {
        return Organizer::query()
            ->where('organizable_type', 'Organization')
            ->where('organizable_id', $organization->id)
            ->whereNull('deleted_at')
            ->first();
    }

    /**
     * @param  array<string>|null  $a
     * @param  array<string>|null  $b
     * @return array<string>|null
     */
    private function mergeStringLists(?array $a, ?array $b): ?array
    {
        $merged = array_values(array_unique(array_merge($a ?? [], $b ?? [])));

        return $merged !== [] ? $merged : null;
    }

    private function isEmptyString(mixed $value): bool
    {
        if ($value === null) {
            return true;
        }

        return is_string($value) && trim($value) === '';
    }
}
