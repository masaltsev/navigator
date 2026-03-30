<?php

namespace App\Filament\Resources\EventResource\Pages;

use App\Filament\Resources\EventResource;
use Filament\Actions;
use Filament\Resources\Components\Tab;
use Filament\Resources\Pages\ListRecords;
use Illuminate\Database\Eloquent\Builder;

class ListEvents extends ListRecords
{
    protected static string $resource = EventResource::class;

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
