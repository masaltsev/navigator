"""Tests for api/harvest_api.py — FastAPI harvest trigger endpoints."""

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create a test client, mocking Celery to avoid Redis dependency."""
    with patch.dict("os.environ", {"HARVESTER_API_TOKEN": ""}):
        from api.harvest_api import app
        return TestClient(app)


class TestHealthEndpoint:
    def test_health_returns_ok(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "harvester"


class TestHarvestRunEndpoint:
    def test_empty_sources(self, client):
        response = client.post("/harvest/run", json={"sources": []})
        assert response.status_code == 200
        assert response.json()["status"] == "empty"

    @patch("api.harvest_api.crawl_and_enrich", create=True)
    def test_dispatch_with_sources(self, mock_task, client):
        mock_result = MagicMock()
        mock_result.id = "test-group-id"

        with patch("celery.group") as mock_group:
            mock_group.return_value.apply_async.return_value = mock_result

            with patch("workers.tasks.crawl_and_enrich") as mock_ce:
                mock_ce.s = MagicMock(return_value=MagicMock())

                response = client.post("/harvest/run", json={
                    "sources": [
                        {"url": "https://a.com", "source_id": "s1"},
                        {"url": "https://b.com", "source_id": "s2"},
                    ],
                    "multi_page": True,
                    "send_to_core": False,
                })

        assert response.status_code == 200

    def test_no_valid_urls(self, client):
        response = client.post("/harvest/run", json={
            "sources": [{"source_id": "no-url"}],
        })
        assert response.status_code == 200
        assert response.json()["status"] == "empty"


class TestHarvestStatusEndpoint:
    @patch("api.harvest_api.AsyncResult", create=True)
    def test_status_pending(self, mock_ar, client):
        mock_result = MagicMock()
        mock_result.state = "PENDING"
        mock_result.ready.return_value = False
        mock_result.failed.return_value = False

        with patch("celery.result.AsyncResult", return_value=mock_result):
            response = client.get("/harvest/status/test-task-id")

        assert response.status_code == 200
