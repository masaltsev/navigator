<?php

use App\Http\Controllers\Api\V1\EventController;
use App\Http\Controllers\Api\V1\OrganizationController;
use App\Http\Controllers\Internal\ImportController;
use App\Http\Controllers\Internal\SourceController;
use Illuminate\Support\Facades\Route;

Route::prefix('v1')->group(function () {
    Route::get('/organizations', [OrganizationController::class, 'index']);
    Route::get('/organizations/{id}', [OrganizationController::class, 'show']);

    Route::get('/events', [EventController::class, 'index']);
});

Route::prefix('internal')->middleware('auth.internal')->group(function () {
    Route::post('/import/organizer', [ImportController::class, 'importOrganizer']);
    Route::post('/import/event', [ImportController::class, 'importEvent']);
    Route::post('/import/batch', [ImportController::class, 'importBatch']);

    Route::get('/organizers', [ImportController::class, 'lookupOrganizer']);
    Route::get('/organizations/without-sources', [ImportController::class, 'organizationsWithoutSources']);

    Route::get('/sources', [SourceController::class, 'index']);
    Route::get('/sources/due', [SourceController::class, 'due']);
    Route::get('/sources/{id}', [SourceController::class, 'show']);
    Route::post('/sources', [SourceController::class, 'store']);
    Route::patch('/sources/{id}', [SourceController::class, 'update']);
});
