"""Tests for metrics/collector.py — HarvestMetrics accumulator."""

import pytest
from metrics.collector import HarvestMetrics


class TestHarvestMetrics:
    """Basic accumulation and summary."""

    def test_empty_metrics(self):
        m = HarvestMetrics()
        s = m.summary()
        assert s["total_urls"] == 0
        assert s["success"] == 0
        assert s["errors"] == 0
        assert s["success_rate"] == 0.0

    def test_record_success(self):
        m = HarvestMetrics()
        m.record_url_result({
            "status": "success",
            "decision": "accepted",
            "confidence": 0.92,
            "works_with_elderly": True,
            "venues_count": 2,
            "venues_geocoded": 1,
            "timing": {"crawl_s": 10, "classify_s": 5, "enrich_s": 1, "core_s": 0.5},
            "llm_metrics": {
                "total_input_tokens": 20000,
                "total_output_tokens": 500,
                "cache_hit_rate": 1.0,
            },
        })
        assert m.total_urls == 1
        assert m.success == 1
        assert m.errors == 0
        assert m.accepted == 1
        assert m.works_with_elderly == 1
        assert m.confidence_sum == pytest.approx(0.92)
        assert m.venues_total == 2
        assert m.venues_geocoded == 1
        assert m.total_input_tokens == 20000

    def test_record_error(self):
        m = HarvestMetrics()
        m.record_url_result({"status": "error", "error": "dns_fail"})
        assert m.total_urls == 1
        assert m.errors == 1
        assert m.success == 0

    def test_multiple_records(self):
        m = HarvestMetrics()
        m.record_url_result({
            "status": "success", "decision": "accepted",
            "confidence": 0.95, "works_with_elderly": True,
            "venues_count": 1, "venues_geocoded": 1,
            "timing": {"crawl_s": 10, "classify_s": 5},
            "llm_metrics": {"total_input_tokens": 20000, "total_output_tokens": 500, "cache_hit_rate": 1},
        })
        m.record_url_result({
            "status": "success", "decision": "rejected",
            "confidence": 0.3, "works_with_elderly": False,
            "venues_count": 0, "venues_geocoded": 0,
            "timing": {"crawl_s": 8, "classify_s": 3},
            "llm_metrics": {"total_input_tokens": 18000, "total_output_tokens": 400, "cache_hit_rate": 1},
        })
        m.record_url_result({"status": "error", "error": "timeout"})

        assert m.total_urls == 3
        assert m.success == 2
        assert m.errors == 1
        assert m.accepted == 1
        assert m.rejected == 1
        assert m.confidence_min == pytest.approx(0.3)
        assert m.confidence_max == pytest.approx(0.95)

    def test_summary_decisions(self):
        m = HarvestMetrics()
        for decision in ["accepted", "accepted", "rejected", "needs_review"]:
            m.record_url_result({
                "status": "success", "decision": decision,
                "confidence": 0.8, "venues_count": 0, "venues_geocoded": 0,
                "timing": {}, "llm_metrics": {},
            })
        s = m.summary()
        assert s["decisions"]["accepted"] == 2
        assert s["decisions"]["rejected"] == 1
        assert s["decisions"]["needs_review"] == 1

    def test_cost_calculation(self):
        m = HarvestMetrics()
        m.total_input_tokens = 1_000_000
        m.total_output_tokens = 100_000
        m.success = 10
        cost = m.estimated_cost_usd
        assert cost == pytest.approx(0.014 + 0.028, rel=0.01)

    def test_cost_per_url(self):
        m = HarvestMetrics()
        m.total_input_tokens = 1_000_000
        m.total_output_tokens = 0
        m.success = 100
        assert m.cost_per_url == pytest.approx(0.014 / 100, rel=0.01)

    def test_success_rate(self):
        m = HarvestMetrics()
        m.total_urls = 10
        m.success = 9
        assert m.success_rate == pytest.approx(0.9)

    def test_summary_structure(self):
        m = HarvestMetrics()
        m.record_url_result({
            "status": "success", "decision": "accepted",
            "confidence": 0.9, "works_with_elderly": True,
            "venues_count": 2, "venues_geocoded": 1,
            "timing": {"crawl_s": 5, "classify_s": 3, "enrich_s": 1, "core_s": 0.5},
            "llm_metrics": {"total_input_tokens": 10000, "total_output_tokens": 300, "cache_hit_rate": 1.0},
        })
        s = m.summary()
        assert "total_urls" in s
        assert "decisions" in s
        assert "confidence" in s
        assert "tokens" in s
        assert "cost" in s
        assert "venues" in s
        assert "timing_avg_s" in s

    def test_thread_safety(self):
        """HarvestMetrics should be safe for concurrent writes."""
        import threading

        m = HarvestMetrics()

        def add_results():
            for _ in range(100):
                m.record_url_result({
                    "status": "success", "decision": "accepted",
                    "confidence": 0.8, "venues_count": 1, "venues_geocoded": 0,
                    "timing": {"crawl_s": 1}, "llm_metrics": {},
                })

        threads = [threading.Thread(target=add_results) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert m.total_urls == 400
        assert m.success == 400
