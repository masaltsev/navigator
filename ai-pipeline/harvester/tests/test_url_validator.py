"""Tests for enrichment/url_validator.py."""

import pytest
from enrichment.url_validator import validate_url, filter_valid_urls


class TestValidateUrl:
    def test_valid_http(self):
        ok, reason = validate_url("http://example.com")
        assert ok
        assert reason == ""

    def test_valid_https(self):
        ok, reason = validate_url("https://kcson-vologda.gov35.ru/kontakty")
        assert ok

    def test_valid_subdomain(self):
        ok, reason = validate_url("https://irkcson.aln.socinfo.ru/")
        assert ok

    def test_empty_url(self):
        ok, reason = validate_url("")
        assert not ok
        assert reason == "empty_url"

    def test_whitespace_url(self):
        ok, reason = validate_url("   ")
        assert not ok
        assert reason == "empty_url"

    def test_missing_scheme(self):
        ok, reason = validate_url("example.com")
        assert not ok
        assert reason == "missing_scheme"

    def test_no_hostname(self):
        ok, reason = validate_url("https://")
        assert not ok
        assert reason == "no_hostname"

    def test_no_tld(self):
        ok, reason = validate_url("https://localhost")
        assert not ok
        assert reason == "no_tld"

    def test_truncated_domain(self):
        """Real bug from Sprint 3.6: mikh-kcson.ryazan. (truncated TLD)."""
        ok, reason = validate_url("https://mikh-kcson.ryazan.")
        assert not ok

    def test_valid_russian_tld(self):
        ok, _ = validate_url("https://example.ru")
        assert ok

    def test_valid_long_path(self):
        ok, _ = validate_url("https://example.com/very/long/path/to/page.html")
        assert ok


class TestFilterValidUrls:
    def test_all_valid(self):
        sources = [
            {"url": "https://a.com", "source_id": "1"},
            {"url": "https://b.ru", "source_id": "2"},
        ]
        valid, invalid = filter_valid_urls(sources)
        assert len(valid) == 2
        assert len(invalid) == 0

    def test_mixed(self):
        sources = [
            {"url": "https://good.com", "source_id": "1"},
            {"url": "bad-no-scheme.com", "source_id": "2"},
            {"url": "", "source_id": "3"},
            {"url": "https://good2.ru/path", "source_id": "4"},
        ]
        valid, invalid = filter_valid_urls(sources)
        assert len(valid) == 2
        assert len(invalid) == 2
        assert invalid[0]["_invalid_reason"] == "missing_scheme"
        assert invalid[1]["_invalid_reason"] == "empty_url"

    def test_empty_input(self):
        valid, invalid = filter_valid_urls([])
        assert valid == []
        assert invalid == []
