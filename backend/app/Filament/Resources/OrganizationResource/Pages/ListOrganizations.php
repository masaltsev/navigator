<?php

namespace App\Filament\Resources\OrganizationResource\Pages;

use App\Filament\Resources\OrganizationResource;
use Filament\Actions;
use Filament\Resources\Components\Tab;
use Filament\Resources\Pages\ListRecords;
use Illuminate\Database\Eloquent\Builder;

class ListOrganizations extends ListRecords
{
    protected static string $resource = OrganizationResource::class;

    public function getTabs(): array
    {
        return [
            'all' => Tab::make('All'),
            'in_review' => Tab::make('In review')
                ->modifyQueryUsing(fn (Builder $query): Builder => $query->where('status', 'in_review')),
            'approved' => Tab::make('Approved')
                ->modifyQueryUsing(fn (Builder $query): Builder => $query->where('status', 'approved')),
        ];
    }

    protected function getHeaderActions(): array
    {
        return [
            Actions\CreateAction::make(),
        ];
    }
}
