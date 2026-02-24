"""
Unit tests for strategies/multi_page.py.

Tests subpage discovery, priority scoring, relevance filtering,
and markdown merging — all without network I/O.
"""

import pytest

from strategies.multi_page import (
    MultiPageCrawler,
    MultiPageResult,
    PageResult,
    SUBPAGE_PATTERNS,
)


class TestSubpageDiscovery:
    """Test _discover_subpages logic with synthetic markdown."""

    def setup_method(self):
        self.crawler = MultiPageCrawler()

    def test_known_patterns_generated(self):
        """Known URL patterns are always generated as candidates."""
        base_url = "https://kcson-vologda.gov35.ru"
        subpages = self.crawler._discover_subpages(base_url, "")
        urls = [url for url, _ in subpages]
        assert any("/kontakty" in u for u in urls)
        assert any("/o-nas" in u for u in urls)
        assert any("/uslugi" in u for u in urls)

    def test_links_from_markdown(self):
        """Internal links in markdown are discovered."""
        base_url = "https://kcson.example.ru"
        markdown = """
        Наш центр предоставляет услуги [Контакты](/nashi-kontakty)
        для получения помощи. [О нас](/about-us)
        """
        subpages = self.crawler._discover_subpages(base_url, markdown)
        urls = [url for url, _ in subpages]
        assert any("nashi-kontakty" in u for u in urls)

    def test_no_duplicate_urls(self):
        """Same URL from pattern and link should appear once."""
        base_url = "https://example.ru"
        markdown = "Перейти на [Контакты](/kontakty)"
        subpages = self.crawler._discover_subpages(base_url, markdown)
        kontakty_urls = [u for u, _ in subpages if "kontakty" in u]
        assert len(kontakty_urls) == 1

    def test_base_url_excluded(self):
        """The base URL itself should not be in subpage list."""
        base_url = "https://example.ru"
        subpages = self.crawler._discover_subpages(base_url, "[Главная](/)")
        urls = [url for url, _ in subpages]
        assert base_url not in urls
        assert base_url + "/" not in urls


class TestRelevanceFilter:
    """Test _is_relevant_subpage filtering."""

    def setup_method(self):
        self.crawler = MultiPageCrawler()

    def test_kontakty_relevant(self):
        assert self.crawler._is_relevant_subpage("/kontakty", "Контакты")

    def test_about_relevant(self):
        assert self.crawler._is_relevant_subpage("/about", "About us")

    def test_uslugi_relevant(self):
        assert self.crawler._is_relevant_subpage("/uslugi", "Услуги")

    def test_news_irrelevant(self):
        assert not self.crawler._is_relevant_subpage("/news/2026/01", "Новости")

    def test_vacancy_irrelevant(self):
        assert not self.crawler._is_relevant_subpage("/vakansii", "Вакансии")

    def test_admin_irrelevant(self):
        assert not self.crawler._is_relevant_subpage("/admin/login", "Вход")

    def test_photo_irrelevant(self):
        assert not self.crawler._is_relevant_subpage("/foto-galereya", "Фото")

    def test_bitrix_irrelevant(self):
        assert not self.crawler._is_relevant_subpage("/bitrix/admin/", "Admin")


class TestPriorityScoring:
    """Test _priority_score ordering."""

    def setup_method(self):
        self.crawler = MultiPageCrawler()

    def test_kontakty_highest(self):
        score = self.crawler._priority_score("https://x.ru/kontakty", "Контакты")
        assert score == 100

    def test_about_medium(self):
        score = self.crawler._priority_score("https://x.ru/o-nas", "О нас")
        assert score == 50

    def test_struktura_lower(self):
        score = self.crawler._priority_score("https://x.ru/struktura", "Структура")
        assert score == 25

    def test_ordering(self):
        """Contacts > About > Structure > Unknown."""
        kontakty = self.crawler._priority_score("https://x.ru/kontakty", "")
        about = self.crawler._priority_score("https://x.ru/o-nas", "")
        struktura = self.crawler._priority_score("https://x.ru/struktura", "")
        other = self.crawler._priority_score("https://x.ru/somepage", "")
        assert kontakty > about > struktura > other


class TestMergePages:
    """Test _merge_pages markdown merging."""

    def setup_method(self):
        self.crawler = MultiPageCrawler()

    def test_merge_successful_pages(self):
        pages = [
            PageResult(url="https://x.ru", label="Главная", markdown="# Main\nContent", success=True),
            PageResult(url="https://x.ru/kontakty", label="Контакты", markdown="# Contacts\nPhone: +7...", success=True),
        ]
        merged = self.crawler._merge_pages(pages)
        assert "Главная" in merged
        assert "Контакты" in merged
        assert "# Main" in merged
        assert "Phone: +7" in merged

    def test_merge_skips_failed(self):
        pages = [
            PageResult(url="https://x.ru", label="Главная", markdown="# Main", success=True),
            PageResult(url="https://x.ru/fail", label="Failed", markdown="", success=False, error="404"),
        ]
        merged = self.crawler._merge_pages(pages)
        assert "Failed" not in merged
        assert "# Main" in merged

    def test_merge_empty_pages(self):
        pages = [
            PageResult(url="https://x.ru", label="Главная", markdown="   ", success=True),
        ]
        merged = self.crawler._merge_pages(pages)
        assert merged == ""

    def test_merge_respects_limit(self):
        long_content = "A" * 20000
        pages = [
            PageResult(url="https://x.ru", label="Главная", markdown=long_content, success=True),
            PageResult(url="https://x.ru/2", label="Page2", markdown=long_content, success=True),
            PageResult(url="https://x.ru/3", label="Page3", markdown=long_content, success=True),
        ]
        merged = self.crawler._merge_pages(pages)
        assert len(merged) <= 35000

    def test_merge_separator(self):
        pages = [
            PageResult(url="https://x.ru", label="A", markdown="AAA", success=True),
            PageResult(url="https://x.ru/b", label="B", markdown="BBB", success=True),
        ]
        merged = self.crawler._merge_pages(pages)
        assert "---" in merged


class TestMultiPageResult:
    def test_success_when_at_least_one_page(self):
        r = MultiPageResult(base_url="https://x.ru", total_pages_success=1)
        assert r.success

    def test_failure_when_no_pages(self):
        r = MultiPageResult(base_url="https://x.ru", total_pages_success=0)
        assert not r.success


class TestSubpagePatterns:
    def test_patterns_not_empty(self):
        assert len(SUBPAGE_PATTERNS) > 0

    def test_patterns_have_labels(self):
        for path, label in SUBPAGE_PATTERNS:
            assert path.startswith("/")
            assert len(label) > 0
