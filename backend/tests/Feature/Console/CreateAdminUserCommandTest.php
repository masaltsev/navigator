<?php

use App\Models\User;
use Tests\Concerns\RefreshDatabaseWithSchema;

uses(RefreshDatabaseWithSchema::class);

test('admin:create creates a new admin user', function (): void {
    $this->artisan('admin:create', [
        'email' => 'adm@example.com',
        'password' => 'secret-password-123',
    ])->assertSuccessful();

    $user = User::query()->where('email', 'adm@example.com')->first();

    expect($user)->not->toBeNull()
        ->and($user->is_admin)->toBeTrue()
        ->and($user->email_verified_at)->not->toBeNull();
});

test('admin:create promotes existing user and updates password', function (): void {
    $user = User::factory()->create([
        'email' => 'existing@example.com',
        'is_admin' => false,
    ]);

    $this->artisan('admin:create', [
        'email' => 'existing@example.com',
        'password' => 'new-secret-password-456',
    ])->assertSuccessful();

    $user->refresh();

    expect($user->is_admin)->toBeTrue();
    $this->assertTrue(\Illuminate\Support\Facades\Hash::check('new-secret-password-456', $user->password));
});
