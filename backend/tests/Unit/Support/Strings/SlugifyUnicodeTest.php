<?php

use App\Support\Strings\SlugifyUnicode;

test('slugifyUnicodePreserveCyrillic preserves cyrillic', function () {
    expect(SlugifyUnicode::slugifyUnicodePreserveCyrillic('Привет мир'))->toBe('привет-мир');
});

test('slugifyUnicodePreserveCyrillic preserves latin', function () {
    expect(SlugifyUnicode::slugifyUnicodePreserveCyrillic('Hello/World'))->toBe('hello-world');
});

test('slugifyUnicodePreserveCyrillic collapses non-alnum to hyphen', function () {
    expect(SlugifyUnicode::slugifyUnicodePreserveCyrillic('  Foo__Bar  '))->toBe('foo-bar');
    expect(SlugifyUnicode::slugifyUnicodePreserveCyrillic('русский---текст'))->toBe('русский-текст');
});

test('slugifyUnicodePreserveCyrillic does not produce leading or trailing hyphens', function () {
    expect(SlugifyUnicode::slugifyUnicodePreserveCyrillic('---Привет---'))->toBe('привет');
});
