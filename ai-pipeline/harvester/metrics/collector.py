"""
Centralized harvest metrics collector.

Accumulates per-URL and aggregate metrics across an entire batch run:
- Token cost (input/output, cache hits)
- Timing breakdown (crawl, classify, enrich, core)
- Success/failure rates by stage
- Decision distribution (accepted/rejected/needs_review)
- Confidence statistics

Thread-safe via a lock for use with Celery concurrent workers.

Usage:
    from metrics.collector import HarvestMetrics

    metrics = HarvestMetrics()
    metrics.record_url_result({...})   # dict returned by _run_pipeline
    print(metrics.summary())
"""

import threading
import time
from dataclasses import dataclass, field

import structlog

logger = structlog.get_logger(__name__)

DEEPSEEK_INPUT_COST_PER_M = 0.014
DEEPSEEK_OUTPUT_COST_PER_M = 0.28
DEEPSEEK_CACHED_INPUT_COST_PER_M = 0.0014


@dataclass
class _StageCounter:
    attempts: int = 0
    successes: int = 0
    failures: int = 0
    total_time_s: float = 0.0

    @property
    def success_rate(self) -> float:
        return self.successes / max(self.attempts, 1)


@dataclass
class HarvestMetrics:
    """Accumulates metrics for a harvest batch run."""

    started_at: float = field(default_factory=time.time)

    total_urls: int = 0
    success: int = 0
    errors: int = 0

    accepted: int = 0
    rejected: int = 0
    needs_review: int = 0

    works_with_elderly: int = 0

    confidence_sum: float = 0.0
    confidence_min: float = 1.0
    confidence_max: float = 0.0

    total_input_tokens: int = 0
    total_output_tokens: int = 0
    cache_hits: int = 0

    venues_total: int = 0
    venues_geocoded: int = 0

    crawl: _StageCounter = field(default_factory=_StageCounter)
    classify: _StageCounter = field(default_factory=_StageCounter)
    enrich: _StageCounter = field(default_factory=_StageCounter)
    core: _StageCounter = field(default_factory=_StageCounter)

    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def record_url_result(self, result: dict) -> None:
        """Record a single URL processing result (output of _run_pipeline or batch_test)."""
        with self._lock:
            self.total_urls += 1

            if result.get("status") == "error":
                self.errors += 1
                return

            self.success += 1

            decision = result.get("decision", "")
            if decision == "accepted":
                self.accepted += 1
            elif decision == "rejected":
                self.rejected += 1
            elif decision == "needs_review":
                self.needs_review += 1

            if result.get("works_with_elderly"):
                self.works_with_elderly += 1

            conf = result.get("confidence", 0.0)
            self.confidence_sum += conf
            self.confidence_min = min(self.confidence_min, conf)
            self.confidence_max = max(self.confidence_max, conf)

            self.venues_total += result.get("venues_count", 0)
            self.venues_geocoded += result.get("venues_geocoded", 0)

            llm = result.get("llm_metrics", {})
            self.total_input_tokens += llm.get("total_input_tokens", 0)
            self.total_output_tokens += llm.get("total_output_tokens", 0)
            if llm.get("cache_hit_rate", 0) > 0:
                self.cache_hits += 1

            timing = result.get("timing", {})
            if timing.get("crawl_s"):
                self.crawl.attempts += 1
                self.crawl.successes += 1
                self.crawl.total_time_s += timing["crawl_s"]
            if timing.get("classify_s"):
                self.classify.attempts += 1
                self.classify.successes += 1
                self.classify.total_time_s += timing["classify_s"]
            if timing.get("enrich_s"):
                self.enrich.attempts += 1
                self.enrich.successes += 1
                self.enrich.total_time_s += timing["enrich_s"]
            if timing.get("core_s"):
                self.core.attempts += 1
                self.core.successes += 1
                self.core.total_time_s += timing["core_s"]

    @property
    def elapsed_s(self) -> float:
        return time.time() - self.started_at

    @property
    def avg_confidence(self) -> float:
        return self.confidence_sum / max(self.success, 1)

    @property
    def estimated_cost_usd(self) -> float:
        return (
            self.total_input_tokens / 1_000_000 * DEEPSEEK_INPUT_COST_PER_M
            + self.total_output_tokens / 1_000_000 * DEEPSEEK_OUTPUT_COST_PER_M
        )

    @property
    def cost_per_url(self) -> float:
        return self.estimated_cost_usd / max(self.success, 1)

    @property
    def success_rate(self) -> float:
        return self.success / max(self.total_urls, 1)

    def summary(self) -> dict:
        """Return a JSON-serializable summary of all collected metrics."""
        return {
            "total_urls": self.total_urls,
            "success": self.success,
            "errors": self.errors,
            "success_rate": round(self.success_rate, 3),
            "elapsed_s": round(self.elapsed_s, 1),
            "avg_time_per_url_s": round(self.elapsed_s / max(self.total_urls, 1), 1),
            "decisions": {
                "accepted": self.accepted,
                "rejected": self.rejected,
                "needs_review": self.needs_review,
            },
            "works_with_elderly": self.works_with_elderly,
            "confidence": {
                "avg": round(self.avg_confidence, 3),
                "min": round(self.confidence_min, 3) if self.success else None,
                "max": round(self.confidence_max, 3) if self.success else None,
            },
            "tokens": {
                "input": self.total_input_tokens,
                "output": self.total_output_tokens,
                "cache_hits": self.cache_hits,
                "cache_hit_rate": round(self.cache_hits / max(self.success, 1), 3),
            },
            "cost": {
                "total_usd": round(self.estimated_cost_usd, 4),
                "per_url_usd": round(self.cost_per_url, 6),
            },
            "venues": {
                "total": self.venues_total,
                "geocoded": self.venues_geocoded,
                "geocode_rate": round(
                    self.venues_geocoded / max(self.venues_total, 1), 3
                ),
            },
            "timing_avg_s": {
                "crawl": round(self.crawl.total_time_s / max(self.crawl.attempts, 1), 1),
                "classify": round(
                    self.classify.total_time_s / max(self.classify.attempts, 1), 1
                ),
                "enrich": round(
                    self.enrich.total_time_s / max(self.enrich.attempts, 1), 1
                ),
                "core": round(self.core.total_time_s / max(self.core.attempts, 1), 1),
            },
        }

    def log_summary(self) -> None:
        """Emit a structured log with the full summary."""
        s = self.summary()
        logger.info(
            "harvest_batch_complete",
            total=s["total_urls"],
            success=s["success"],
            errors=s["errors"],
            success_rate=s["success_rate"],
            accepted=s["decisions"]["accepted"],
            rejected=s["decisions"]["rejected"],
            cost_usd=s["cost"]["total_usd"],
            cost_per_url=s["cost"]["per_url_usd"],
            avg_confidence=s["confidence"]["avg"],
            elapsed_s=s["elapsed_s"],
        )
