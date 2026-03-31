<?php

/*
|--------------------------------------------------------------------------
| Test Environment Bootstrapping
|--------------------------------------------------------------------------
|
| This repo currently contains cached bootstrap files (bootstrap/cache/*.php).
| If they exist, Laravel will load them and ignore phpunit.xml environment
| overrides, which breaks tests (e.g. using file cache with unwritable paths).
|
| NOTE: This file must never attempt to create databases / extensions.
| Tests must run against an explicitly provisioned *_test database.
|
*/

$bootstrapCacheDir = dirname(__DIR__).'/bootstrap/cache';
$cachedFiles = [
    $bootstrapCacheDir.'/config.php',
    $bootstrapCacheDir.'/packages.php',
    $bootstrapCacheDir.'/routes-v7.php',
    $bootstrapCacheDir.'/services.php',
];

foreach ($cachedFiles as $file) {
    if (is_file($file)) {
        @unlink($file);
    }
}

/*
|--------------------------------------------------------------------------
| Test Case
|--------------------------------------------------------------------------
|
| The closure you provide to your test functions is always bound to a specific PHPUnit test
| case class. By default, that class is "PHPUnit\Framework\TestCase". Of course, you may
| need to change it using the "pest()" function to bind a different classes or traits.
|
*/

pest()->extend(Tests\TestCase::class)
    ->use(Tests\Concerns\RefreshDatabaseWithSchema::class)
    ->in('Feature');

/*
|--------------------------------------------------------------------------
| Expectations
|--------------------------------------------------------------------------
|
| When you're writing tests, you often need to check that values meet certain conditions. The
| "expect()" function gives you access to a set of "expectations" methods that you can use
| to assert different things. Of course, you may extend the Expectation API at any time.
|
*/

expect()->extend('toBeOne', function () {
    return $this->toBe(1);
});

/*
|--------------------------------------------------------------------------
| Functions
|--------------------------------------------------------------------------
|
| While Pest is very powerful out-of-the-box, you may have some testing code specific to your
| project that you don't want to repeat in every file. Here you can also expose helpers as
| global functions to help you to reduce the number of lines of code in your test files.
|
*/

function something()
{
    // ..
}
