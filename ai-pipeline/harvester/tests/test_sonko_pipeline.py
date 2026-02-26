"""Tests for SONKO pipeline orchestrator."""

import os
from unittest.mock import AsyncMock, MagicMock

import pytest

from aggregators.sonko.models import SONKOEntry, SONKOOrganization
from aggregators.sonko.sonko_pipeline import PipelineReport, SONKOPipeline
from core_client.api import NavigatorCoreClient
from enrichment.dadata_client import DadataClient

FIXTURE_PATH = os.path.join(
    os.path.dirname(__file__), "fixtures", "sonko_sample.xlsx"
)


@pytest.fixture
def mock_core_client() -> NavigatorCoreClient:
    return NavigatorCoreClient(base_url="", api_token="")


@pytest.fixture
def mock_dadata_client() -> DadataClient:
    return DadataClient(api_key="", secret_key="")


def _make_entry(**overrides) -> SONKOEntry:
    defaults = {
        "inn": "7701234567",
        "full_name": "АНО Социальная помощь пожилым",
        "short_name": "АНО Соцпомощь",
        "address": "Москва, ул. Тестовая, 1",
        "ogrn": "1027700000001",
        "okved": "88.10",
        "sonko_status": "Поставщик социальных услуг",
    }
    defaults.update(overrides)
    return SONKOEntry(**defaults)


def _make_organization(**overrides) -> SONKOOrganization:
    entry = _make_entry()
    defaults = {
        "inn": "7701234567",
        "ogrn": "1027700000001",
        "full_name": "АНО Социальная помощь пожилым",
        "short_name": "АНО Соцпомощь",
        "address": "Москва, ул. Тестовая, 1",
        "okved": "88.10",
        "entries": [entry],
    }
    defaults.update(overrides)
    return SONKOOrganization(**defaults)


class TestBuildSonkoContext:
    def test_contains_org_info(self):
        org = _make_organization()
        ctx = SONKOPipeline._build_sonko_context(org)
        assert "АНО Социальная помощь пожилым" in ctx
        assert "7701234567" in ctx
        assert "88.10" in ctx

    def test_contains_short_name(self):
        org = _make_organization()
        ctx = SONKOPipeline._build_sonko_context(org)
        assert "АНО Соцпомощь" in ctx

    def test_contains_statuses(self):
        org = _make_organization()
        ctx = SONKOPipeline._build_sonko_context(org)
        assert "Поставщик социальных услуг" in ctx

    def test_elderly_mention(self):
        org = _make_organization()
        ctx = SONKOPipeline._build_sonko_context(org)
        assert "старшего возраста" in ctx


class TestPipelineAnalyze:
    @pytest.mark.asyncio
    async def test_analyze_only(self, mock_core_client, mock_dadata_client):
        pipeline = SONKOPipeline(
            core_client=mock_core_client,
            dadata_client=mock_dadata_client,
        )
        stats = await pipeline.analyze_only(FIXTURE_PATH)

        assert stats.total_entries == 8
        assert stats.combined_unique > 0

    @pytest.mark.asyncio
    async def test_analyze_with_broader_okved(self, mock_core_client, mock_dadata_client):
        pipeline = SONKOPipeline(
            core_client=mock_core_client,
            dadata_client=mock_dadata_client,
        )
        narrow = await pipeline.analyze_only(FIXTURE_PATH, include_broader_okved=False)
        broad = await pipeline.analyze_only(FIXTURE_PATH, include_broader_okved=True)

        assert broad.after_okved >= narrow.after_okved


class TestPipelineDryRun:
    @pytest.mark.asyncio
    async def test_dry_run_returns_report(self, mock_core_client, mock_dadata_client):
        pipeline = SONKOPipeline(
            core_client=mock_core_client,
            dadata_client=mock_dadata_client,
            delay_between_orgs=0,
        )
        report = await pipeline.run(
            xlsx_path=FIXTURE_PATH,
            limit=3,
            dry_run=True,
        )

        assert isinstance(report, PipelineReport)
        assert len(report.results) <= 3
        for r in report.results:
            assert r.action == "dry_run"

    @pytest.mark.asyncio
    async def test_report_to_dict(self, mock_core_client, mock_dadata_client):
        pipeline = SONKOPipeline(
            core_client=mock_core_client,
            dadata_client=mock_dadata_client,
            delay_between_orgs=0,
        )
        report = await pipeline.run(
            xlsx_path=FIXTURE_PATH,
            limit=2,
            dry_run=True,
        )

        d = report.to_dict()
        assert "filter_stats" in d
        assert "results" in d
        assert "summary" in d


class TestPipelineMockMode:
    @pytest.mark.asyncio
    async def test_mock_mode_creates_orgs(self):
        pipeline = SONKOPipeline(
            core_client=NavigatorCoreClient(base_url="", api_token=""),
            dadata_client=DadataClient(api_key=""),
            delay_between_orgs=0,
        )
        report = await pipeline.run(
            xlsx_path=FIXTURE_PATH,
            limit=2,
            dry_run=False,
        )

        assert isinstance(report, PipelineReport)
        for r in report.results:
            assert r.action in ("created_minimal", "created", "error")


class TestPipelineMatchedOrg:
    @pytest.mark.asyncio
    async def test_matched_org_gets_updated(self):
        existing = {
            "organizer_id": "org-55",
            "title": "Existing SONKO Org",
            "description": "Old desc",
            "ai_metadata": {
                "decision": "accepted",
                "ai_confidence_score": 0.9,
                "ai_source_trace": [],
            },
        }

        mock_core = AsyncMock()
        mock_core.lookup_organization = AsyncMock(return_value=existing)
        mock_core.import_organizer = AsyncMock(return_value={"organizer_id": "org-55"})

        pipeline = SONKOPipeline(
            core_client=mock_core,
            dadata_client=DadataClient(api_key=""),
            delay_between_orgs=0,
        )

        org = _make_organization()
        result = await pipeline._process_organization(org, dry_run=False)

        assert result.action == "matched"
        assert result.core_organizer_id == "org-55"

        mock_core.import_organizer.assert_called_once()
        update_payload = mock_core.import_organizer.call_args[0][0]
        assert "СО НКО" in update_payload["description"]
        trace_kinds = [t["source_kind"] for t in update_payload["ai_metadata"]["ai_source_trace"]]
        assert "registry_sonko" in trace_kinds
