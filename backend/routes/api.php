<?php

use App\Http\Controllers\Api\V1\EventController;
use App\Http\Controllers\Api\V1\OrganizationController;
use App\Http\Controllers\Internal\ImportController;
use Illuminate\Support\Facades\Route;

Route::prefix('v1')->group(function () {
    Route::get('/organizations', [OrganizationController::class, 'index']);
    Route::get('/organizations/{id}', [OrganizationController::class, 'show']);

    Route::get('/events', [EventController::class, 'index']);
});

// Internal API for AI pipeline (requires authentication)
// TODO: Add authentication middleware (e.g., auth:sanctum or API key middleware)
Route::prefix('internal')->group(function () {
    Route::post('/import/organizer', [ImportController::class, 'importOrganizer']);
    Route::post('/import/event', [ImportController::class, 'importEvent']);
    Route::post('/import/batch', [ImportController::class, 'importBatch']);
});
