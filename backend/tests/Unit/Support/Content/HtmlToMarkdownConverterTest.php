<?php

use App\Support\Content\HtmlToMarkdownConverter;

test('looksLikeHtml detects html tags', function () {
    expect(HtmlToMarkdownConverter::looksLikeHtml('Hello world'))->toBeFalse();
    expect(HtmlToMarkdownConverter::looksLikeHtml('<p>Hello</p>'))->toBeTrue();
});

test('convert supports basic paragraphs and br', function () {
    $md = HtmlToMarkdownConverter::convert('<p>Hello<br/>World</p>');
    expect($md)->toBe('Hello'."\n".'World');
});

test('convert supports strong/em emphasis', function () {
    $md = HtmlToMarkdownConverter::convert('<p><strong>Bold</strong> and <em>Italic</em></p>');
    expect($md)->toContain('**Bold**');
    expect($md)->toContain('*Italic*');
});

test('convert supports links', function () {
    $md = HtmlToMarkdownConverter::convert('<a href="https://example.com">Site</a>');
    expect($md)->toBe('[Site](https://example.com)');
});

test('convert supports unordered lists', function () {
    $md = HtmlToMarkdownConverter::convert('<ul><li>One</li><li>Two</li></ul>');
    expect($md)->toBe('- One'."\n".'- Two');
});

test('convert supports ordered lists', function () {
    $md = HtmlToMarkdownConverter::convert('<ol><li>One</li><li>Two</li></ol>');
    expect($md)->toBe('1. One'."\n".'2. Two');
});

test('convert supports blockquotes', function () {
    $md = HtmlToMarkdownConverter::convert('<blockquote><p>Quote</p></blockquote>');
    expect($md)->toContain('> Quote');
});

test('convert supports headings', function () {
    $md = HtmlToMarkdownConverter::convert('<h2>Title</h2>');
    expect($md)->toBe('## Title');
});
