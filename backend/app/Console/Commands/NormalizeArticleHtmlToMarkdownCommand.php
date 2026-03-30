<?php

namespace App\Console\Commands;

use App\Models\Article;
use App\Support\Content\HtmlToMarkdownConverter;
use Illuminate\Console\Command;

class NormalizeArticleHtmlToMarkdownCommand extends Command
{
    protected $signature = 'articles:normalize-html-to-markdown {--dry-run : Do not persist changes} {--limit=0 : Max processed articles (0 = no limit)}';

    protected $description = 'Convert legacy HTML in articles.content to Markdown';

    public function handle(): int
    {
        $dryRun = (bool) $this->option('dry-run');
        $limit = (int) $this->option('limit');

        $processed = 0;
        $updated = 0;

        $query = Article::query()
            ->whereNotNull('content')
            ->where('content', 'like', '%<%');

        foreach ($query->cursor() as $article) {
            $processed++;

            $content = (string) $article->content;
            if (! HtmlToMarkdownConverter::looksLikeHtml($content)) {
                continue;
            }

            $converted = HtmlToMarkdownConverter::convert($content);
            if ($converted === $content) {
                continue;
            }

            if (! $dryRun) {
                $article->content = $converted;
                $article->save();
            }

            $updated++;

            if ($limit > 0 && $processed >= $limit) {
                break;
            }
        }

        $this->info(sprintf(
            'Processed %d article(s); %d would be updated (%s).',
            $processed,
            $updated,
            $dryRun ? 'dry-run' : 'persisted'
        ));

        return self::SUCCESS;
    }
}
