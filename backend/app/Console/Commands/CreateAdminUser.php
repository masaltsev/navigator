<?php

namespace App\Console\Commands;

use App\Models\User;
use Illuminate\Console\Command;

class CreateAdminUser extends Command
{
    /**
     * The name and signature of the console command.
     *
     * @var string
     */
    protected $signature = 'admin:create {email} {password}';

    /**
     * The console command description.
     *
     * @var string
     */
    protected $description = 'Create or update a user with full Filament admin access';

    /**
     * Execute the console command.
     */
    public function handle(): int
    {
        $email = (string) $this->argument('email');
        $password = (string) $this->argument('password');

        $user = User::query()->where('email', $email)->first();

        if ($user) {
            $user->forceFill([
                'is_admin' => true,
                'password' => $password,
                'email_verified_at' => now(),
            ])->save();

            $this->info("Updated existing user [{$email}] as admin.");

            return self::SUCCESS;
        }

        User::query()->create([
            'name' => explode('@', $email, 2)[0] ?: 'Admin',
            'email' => $email,
            'password' => $password,
            'is_admin' => true,
            'email_verified_at' => now(),
        ]);

        $this->info("Created admin user [{$email}].");

        return self::SUCCESS;
    }
}
