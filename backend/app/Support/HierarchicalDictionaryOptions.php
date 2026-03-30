<?php

namespace App\Support;

use Illuminate\Database\Eloquent\Model;

/**
 * Build tree-ordered options for any Eloquent model with a self-referencing parent_id.
 * Options are returned in DFS order: parent, then its children sorted alphabetically.
 */
class HierarchicalDictionaryOptions
{
    /**
     * @param  class-string<Model>  $modelClass
     * @return array<int|string, string>
     */
    public static function options(string $modelClass, string $labelColumn = 'name', string $parentColumn = 'parent_id'): array
    {
        $model = new $modelClass;
        $keyName = $model->getKeyName();

        $rows = $modelClass::query()
            ->select([$keyName, $labelColumn, $parentColumn])
            ->get();

        $childrenByParent = [];
        foreach ($rows as $row) {
            $parentKey = $row->{$parentColumn};
            $childrenByParent[$parentKey][] = $row;
        }

        foreach ($childrenByParent as &$children) {
            usort($children, static fn (Model $a, Model $b): int => strcmp($a->{$labelColumn}, $b->{$labelColumn}));
        }
        unset($children);

        $options = [];

        $walk = function ($parentId, int $depth) use (&$walk, &$options, $childrenByParent, $labelColumn, $keyName): void {
            foreach ($childrenByParent[$parentId] ?? [] as $child) {
                $prefix = $depth > 0 ? str_repeat('— ', $depth) : '';
                $options[$child->{$keyName}] = $prefix.$child->{$labelColumn};
                $walk($child->{$keyName}, $depth + 1);
            }
        };

        $walk(null, 0);

        return $options;
    }
}
