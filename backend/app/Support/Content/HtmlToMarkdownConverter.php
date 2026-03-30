<?php

namespace App\Support\Content;

use DOMDocument;
use DOMElement;
use DOMNode;

class HtmlToMarkdownConverter
{
    public static function looksLikeHtml(string $value): bool
    {
        if ($value === '') {
            return false;
        }

        // Quick heuristic: a tag-like construct.
        return (bool) preg_match('/<\s*[a-z][^>]*>/i', $value);
    }

    public static function convert(string $html): string
    {
        if ($html === '') {
            return '';
        }

        if (! self::looksLikeHtml($html)) {
            return $html;
        }

        $dom = new DOMDocument('1.0', 'UTF-8');
        $internalErrors = libxml_use_internal_errors(true);

        // Wrap into a single root to simplify traversal.
        $wrapped = '<div>'.$html.'</div>';
        $dom->loadHTML(
            '<?xml encoding="utf-8" ?>'.$wrapped,
            LIBXML_HTML_NOIMPLIED | LIBXML_HTML_NODEFDTD | LIBXML_NOERROR | LIBXML_NOWARNING
        );

        libxml_clear_errors();
        libxml_use_internal_errors($internalErrors);

        $root = $dom->getElementsByTagName('div')->item(0);
        if (! $root) {
            return trim($html);
        }

        $markdown = self::renderChildren($root);

        // Normalize whitespace a bit for stable output.
        $markdown = preg_replace("/\n{3,}/", "\n\n", (string) $markdown);

        return trim((string) $markdown);
    }

    private static function renderChildren(DOMNode $node): string
    {
        $parts = [];

        foreach ($node->childNodes as $child) {
            $rendered = self::renderNode($child);
            if ($rendered !== '') {
                $parts[] = $rendered;
            }
        }

        return implode('', $parts);
    }

    private static function renderNode(DOMNode $node): string
    {
        if ($node->nodeType === XML_TEXT_NODE) {
            return self::normalizeInlineText($node->nodeValue);
        }

        if (! ($node instanceof DOMElement)) {
            return '';
        }

        // Remove script/style blocks completely.
        $tag = strtolower($node->tagName);
        if (in_array($tag, ['script', 'style'], true)) {
            return '';
        }

        return match ($tag) {
            'br' => "\n",
            'p' => self::renderParagraph($node),
            'div' => self::renderChildren($node),
            'strong', 'b' => '**'.self::renderChildren($node).'**',
            'em', 'i' => '*'.self::renderChildren($node).'*',
            'a' => self::renderLink($node),
            'h1', 'h2', 'h3', 'h4', 'h5', 'h6' => self::renderHeading($node),
            'ul' => self::renderList($node, 'ul'),
            'ol' => self::renderList($node, 'ol'),
            'li' => self::renderListItem($node),
            'blockquote' => self::renderBlockquote($node),
            'code' => '`'.self::renderChildren($node).'`',
            'img' => self::renderImage($node),
            default => self::renderChildren($node),
        };
    }

    private static function renderParagraph(DOMElement $node): string
    {
        $content = trim(self::renderChildren($node));
        if ($content === '') {
            return '';
        }

        return $content."\n\n";
    }

    private static function renderHeading(DOMElement $node): string
    {
        $tag = strtolower($node->tagName);
        $level = match ($tag) {
            'h1' => 1,
            'h2' => 2,
            'h3' => 3,
            'h4' => 4,
            'h5' => 5,
            'h6' => 6,
            default => 1,
        };

        $content = trim(self::renderChildren($node));
        if ($content === '') {
            return '';
        }

        return str_repeat('#', $level).' '.$content."\n\n";
    }

    private static function renderLink(DOMElement $node): string
    {
        $href = (string) $node->getAttribute('href');
        $text = trim(self::renderChildren($node));

        if ($text === '') {
            return $href !== '' ? '<'.$href.'>' : '';
        }

        if ($href === '') {
            return $text;
        }

        return '['.$text.']('.$href.')';
    }

    private static function renderImage(DOMElement $node): string
    {
        $src = (string) $node->getAttribute('src');
        $alt = (string) $node->getAttribute('alt');

        if ($src === '') {
            return '';
        }

        return '!['.($alt !== '' ? $alt : 'image').']('.$src.')';
    }

    private static function renderBlockquote(DOMElement $node): string
    {
        $content = trim(self::renderChildren($node));
        if ($content === '') {
            return '';
        }

        $lines = preg_split('/\R/', (string) $content) ?: [];
        $quoted = array_map(static fn (string $line): string => '> '.$line, $lines);

        return implode("\n", $quoted)."\n\n";
    }

    private static function renderList(DOMElement $node, string $type): string
    {
        $items = [];
        $index = 1;

        foreach ($node->childNodes as $child) {
            if (! ($child instanceof DOMElement) || strtolower($child->tagName) !== 'li') {
                continue;
            }

            $itemText = trim(self::renderChildren($child));
            if ($itemText === '') {
                continue;
            }

            if ($type === 'ol') {
                $items[] = $index.'. '.$itemText;
                $index++;
            } else {
                $items[] = '- '.$itemText;
            }
        }

        if ($items === []) {
            return '';
        }

        return implode("\n", $items)."\n\n";
    }

    private static function renderListItem(DOMElement $node): string
    {
        // Standalone <li> without context shouldn't happen in our use, but handle gracefully.
        $text = trim(self::renderChildren($node));

        return $text !== '' ? $text : '';
    }

    private static function normalizeInlineText(?string $text): string
    {
        $text = (string) ($text ?? '');
        if (trim($text) === '') {
            return '';
        }

        // DOMDocument can preserve many whitespace artifacts. Collapse them for stable output.
        $text = html_entity_decode($text, ENT_QUOTES | ENT_HTML5, 'UTF-8');
        $text = preg_replace('/\s+/u', ' ', $text);

        return $text;
    }
}
