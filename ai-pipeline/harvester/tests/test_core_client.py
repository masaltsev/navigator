"""
Unit tests for core_client/api.py.

Tests mock mode (no network) and payload validation.
"""

import asyncio

import pytest

from core_client.api import CoreApiError, NavigatorCoreClient


def _make_valid_payload(**overrides) -> dict:
    """Minimal valid payload matching ImportController contract."""
    payload = {
        "source_reference": "test-ref-001",
        "entity_type": "Organization",
        "title": "КЦСОН г. Вологды",
        "description": "Центр социального обслуживания",
        "inn": "3525155950",
        "ogrn": "1043500037498",
        "ai_metadata": {
            "decision": "accepted",
            "ai_explanation": "КЦСОН с отделением для пожилых",
            "ai_confidence_score": 0.95,
            "works_with_elderly": True,
        },
        "classification": {
            "organization_type_codes": ["141"],
            "ownership_type_code": "154",
            "thematic_category_codes": ["7"],
            "service_codes": ["70"],
            "specialist_profile_codes": [],
        },
        "venues": [
            {"address_raw": "г. Вологда, ул. Козлёнская, 35"}
        ],
        "contacts": {
            "phones": ["+7 (8172) 72-13-44"],
            "emails": ["kcson@gov35.ru"],
        },
        "target_audience": ["elderly"],
    }
    payload.update(overrides)
    return payload


class TestMockMode:
    """NavigatorCoreClient with no base_url operates in mock mode."""

    def test_mock_mode_default(self):
        client = NavigatorCoreClient()
        assert client.mock_mode

    def test_real_mode_with_url(self):
        client = NavigatorCoreClient(base_url="http://localhost:8000")
        assert not client.mock_mode

    def test_mock_import_accepted_approved(self):
        client = NavigatorCoreClient()
        payload = _make_valid_payload()
        resp = asyncio.run(client.import_organizer(payload))
        assert resp["status"] == "success"
        assert resp["assigned_status"] == "approved"
        assert resp["_mock"] is True

    def test_mock_import_accepted_low_confidence(self):
        client = NavigatorCoreClient()
        payload = _make_valid_payload()
        payload["ai_metadata"]["ai_confidence_score"] = 0.70
        resp = asyncio.run(client.import_organizer(payload))
        assert resp["assigned_status"] == "pending_review"

    def test_mock_import_accepted_not_elderly(self):
        client = NavigatorCoreClient()
        payload = _make_valid_payload()
        payload["ai_metadata"]["works_with_elderly"] = False
        resp = asyncio.run(client.import_organizer(payload))
        assert resp["assigned_status"] == "pending_review"

    def test_mock_import_needs_review(self):
        client = NavigatorCoreClient()
        payload = _make_valid_payload()
        payload["ai_metadata"]["decision"] = "needs_review"
        resp = asyncio.run(client.import_organizer(payload))
        assert resp["assigned_status"] == "pending_review"

    def test_mock_import_rejected(self):
        client = NavigatorCoreClient()
        payload = _make_valid_payload()
        payload["ai_metadata"]["decision"] = "rejected"
        payload["ai_metadata"]["ai_confidence_score"] = 0.3
        payload["ai_metadata"]["works_with_elderly"] = False
        resp = asyncio.run(client.import_organizer(payload))
        assert resp["assigned_status"] == "rejected"

    def test_mock_validation_missing_fields(self):
        client = NavigatorCoreClient()
        with pytest.raises(CoreApiError) as exc_info:
            asyncio.run(client.import_organizer({"incomplete": True}))
        assert exc_info.value.status_code == 422
        assert "missing required fields" in str(exc_info.value)

    def test_mock_batch(self):
        client = NavigatorCoreClient()
        items = [_make_valid_payload(), _make_valid_payload()]
        resp = asyncio.run(client.import_batch(items))
        assert resp["status"] == "accepted"
        assert resp["items_count"] == 2

    def test_mock_event(self):
        client = NavigatorCoreClient()
        payload = {
            "source_reference": "event-001",
            "title": "Концерт для пожилых",
            "ai_metadata": {
                "decision": "accepted",
                "ai_confidence_score": 0.88,
                "works_with_elderly": True,
            },
        }
        resp = asyncio.run(client.import_event(payload))
        assert resp["status"] == "success"


class TestMetrics:
    def test_initial_metrics(self):
        client = NavigatorCoreClient()
        metrics = client.get_metrics()
        assert metrics["total_calls"] == 0
        assert metrics["mock_mode"] is True

    def test_metrics_after_calls(self):
        client = NavigatorCoreClient()
        payload = _make_valid_payload()
        asyncio.run(client.import_organizer(payload))
        asyncio.run(client.import_organizer(payload))
        metrics = client.get_metrics()
        assert metrics["total_calls"] == 2
        assert metrics["successful"] == 2
        assert metrics["failed"] == 0


class TestCoreApiError:
    def test_error_representation(self):
        err = CoreApiError(422, "Validation failed", {"errors": {"title": ["required"]}})
        assert "422" in str(err)
        assert "Validation failed" in str(err)
        assert err.body is not None
