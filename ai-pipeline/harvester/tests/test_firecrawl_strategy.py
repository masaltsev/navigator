"""Tests for strategies/firecrawl_strategy.py — Firecrawl client (unit, no network)."""

import pytest
from strategies.firecrawl_strategy import FirecrawlClient, FirecrawlResult


class TestFirecrawlClientDisabled:
    """FirecrawlClient without API key should gracefully return failures."""

    def test_not_enabled_without_key(self):
        client = FirecrawlClient(api_key="")
        assert not client.enabled

    def test_enabled_with_key(self):
        client = FirecrawlClient(api_key="test-key-123")
        assert client.enabled

    @pytest.mark.asyncio
    async def test_scrape_disabled_returns_failure(self):
        client = FirecrawlClient(api_key="")
        result = await client.scrape("https://example.com")
        assert not result.success
        assert "not configured" in result.error

    def test_metrics_empty(self):
        client = FirecrawlClient(api_key="")
        metrics = client.get_metrics()
        assert metrics["total_calls"] == 0
        assert metrics["successful"] == 0
        assert metrics["failed"] == 0


class TestFirecrawlResult:
    def test_success_result(self):
        r = FirecrawlResult(url="https://a.com", markdown="# Title", success=True)
        assert r.success
        assert r.markdown == "# Title"

    def test_failure_result(self):
        r = FirecrawlResult(url="https://a.com", markdown="", success=False, error="timeout")
        assert not r.success
        assert r.error == "timeout"


class TestFirecrawlMetrics:
    @pytest.mark.asyncio
    async def test_disabled_call_does_not_increment_calls(self):
        client = FirecrawlClient(api_key="")
        await client.scrape("https://example.com")
        assert client.get_metrics()["total_calls"] == 0

    @pytest.mark.asyncio
    async def test_multi_page_disabled(self):
        client = FirecrawlClient(api_key="")
        results = await client.scrape_multi_page([
            ("https://a.com", "A"),
            ("https://b.com", "B"),
        ])
        assert len(results) == 2
        assert all(not r.success for r in results)
