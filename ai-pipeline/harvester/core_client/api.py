"""
HTTP client for Navigator Core Internal API.

Endpoints:
  POST /api/internal/import/organizer  — send enriched organization payload
  POST /api/internal/import/event      — send enriched event payload
  POST /api/internal/import/batch      — send batch of items (stub in Core)

The client is async (httpx) and includes retry logic for transient failures.
When core_api_url is empty, operates in mock mode — validates payload locally
and returns a synthetic response without network calls.
"""

import json
import logging
from typing import Optional

import httpx
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)


class CoreApiError(Exception):
    """Raised when Core API returns a non-2xx response."""

    def __init__(self, status_code: int, detail: str, body: Optional[dict] = None):
        self.status_code = status_code
        self.detail = detail
        self.body = body
        super().__init__(f"Core API error {status_code}: {detail}")


class NavigatorCoreClient:
    """
    Async HTTP client for Navigator Core internal API.

    Mock mode: when base_url is empty, all calls return synthetic success
    responses without network I/O. Useful for development and testing
    when the Core backend isn't running.
    """

    def __init__(
        self,
        base_url: str = "",
        api_token: str = "",
        timeout: float = 30.0,
    ):
        self._base_url = base_url.rstrip("/") if base_url else ""
        self._api_token = api_token
        self._timeout = timeout
        self._mock_mode = not bool(base_url)

        self._total_calls = 0
        self._successful = 0
        self._failed = 0

        if self._mock_mode:
            logger.info("NavigatorCoreClient initialized in MOCK mode (no base_url)")
        else:
            logger.info("NavigatorCoreClient initialized: %s", self._base_url)

    @property
    def mock_mode(self) -> bool:
        return self._mock_mode

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type(
            (httpx.ConnectError, httpx.TimeoutException, httpx.ReadTimeout)
        ),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    async def import_organizer(self, payload: dict) -> dict:
        """
        POST /api/internal/import/organizer

        Sends an OrganizationImportPayload to Core and returns the response.
        In mock mode, validates key fields and returns a synthetic response.
        """
        self._total_calls += 1

        if self._mock_mode:
            return self._mock_import_response(payload, "organizer")

        url = f"{self._base_url}/api/internal/import/organizer"
        return await self._post(url, payload)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type(
            (httpx.ConnectError, httpx.TimeoutException, httpx.ReadTimeout)
        ),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    async def import_event(self, payload: dict) -> dict:
        """POST /api/internal/import/event"""
        self._total_calls += 1

        if self._mock_mode:
            return self._mock_import_response(payload, "event")

        url = f"{self._base_url}/api/internal/import/event"
        return await self._post(url, payload)

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=2, max=15),
        retry=retry_if_exception_type(
            (httpx.ConnectError, httpx.TimeoutException)
        ),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    async def import_batch(self, items: list[dict]) -> dict:
        """POST /api/internal/import/batch"""
        self._total_calls += 1

        if self._mock_mode:
            return {
                "status": "accepted",
                "message": "Batch import queued (mock)",
                "job_id": "mock-batch-001",
                "items_count": len(items),
            }

        url = f"{self._base_url}/api/internal/import/batch"
        return await self._post(url, {"items": items})

    async def _post(self, url: str, payload: dict) -> dict:
        """Execute a POST request with auth headers and error handling."""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self._api_token:
            headers["Authorization"] = self._api_token

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(url, json=payload, headers=headers)

        if resp.status_code in (200, 201, 202):
            self._successful += 1
            return resp.json()

        self._failed += 1
        try:
            error_body = resp.json()
        except (json.JSONDecodeError, ValueError):
            error_body = {"raw": resp.text[:500]}

        detail = error_body.get("message", resp.text[:200])
        raise CoreApiError(resp.status_code, detail, error_body)

    def _mock_import_response(self, payload: dict, entity_kind: str) -> dict:
        """Validate payload structure and return a synthetic response."""
        required = ["source_reference", "title", "ai_metadata"]
        missing = [f for f in required if f not in payload]
        if missing:
            self._failed += 1
            raise CoreApiError(
                422,
                f"Mock validation: missing required fields: {missing}",
                {"missing_fields": missing},
            )

        self._successful += 1
        import uuid

        mock_id = str(uuid.uuid4())
        decision = payload.get("ai_metadata", {}).get("decision", "unknown")
        confidence = payload.get("ai_metadata", {}).get("ai_confidence_score", 0)
        works_with_elderly = payload.get("ai_metadata", {}).get("works_with_elderly", False)

        if decision == "rejected":
            status = "rejected"
        elif decision == "needs_review":
            status = "pending_review"
        elif decision == "accepted" and confidence >= 0.85 and works_with_elderly:
            status = "approved"
        elif decision == "accepted":
            status = "pending_review"
        else:
            status = "draft"

        logger.info(
            "MOCK %s import: '%s' → status=%s (decision=%s, confidence=%.2f)",
            entity_kind,
            payload.get("title", "?")[:60],
            status,
            decision,
            confidence,
        )

        return {
            "status": "success",
            "organizer_id": mock_id,
            "entity_id": str(uuid.uuid4()),
            "entity_type": payload.get("entity_type", "Organization"),
            "assigned_status": status,
            "_mock": True,
        }

    def get_metrics(self) -> dict:
        return {
            "total_calls": self._total_calls,
            "successful": self._successful,
            "failed": self._failed,
            "success_rate": self._successful / max(self._total_calls, 1),
            "mock_mode": self._mock_mode,
        }
