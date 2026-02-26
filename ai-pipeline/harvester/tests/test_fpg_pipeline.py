"""Tests for FPG pipeline orchestrator."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aggregators.fpg.fpg_pipeline import FPGPipeline, PipelineReport
from aggregators.fpg.models import FPGOrganization, FPGProject
from core_client.api import NavigatorCoreClient
from enrichment.dadata_client import DadataClient

FIXTURE_PATH = os.path.join(
    os.path.dirname(__file__), "fixtures", "fpg_sample.xlsx"
)


@pytest.fixture
def mock_core_client() -> NavigatorCoreClient:
    client = NavigatorCoreClient(base_url="", api_token="")
    return client


@pytest.fixture
def mock_dadata_client() -> DadataClient:
    return DadataClient(api_key="", secret_key="")


def _make_project(**overrides) -> FPGProject:
    defaults = {
        "application_number": "17-1-000001",
        "contest": "First Contest 2017",
        "organization_name": "Test Org",
        "inn": "7701234567",
        "ogrn": "1027700000001",
        "region": "Москва",
        "project_title": "Помощь пожилым людям",
        "grant_direction": "Социальное обслуживание",
        "status": "Победитель конкурса",
    }
    defaults.update(overrides)
    return FPGProject(**defaults)


def _make_organization(**overrides) -> FPGOrganization:
    project = _make_project()
    defaults = {
        "inn": "7701234567",
        "ogrn": "1027700000001",
        "name": "Test Org",
        "region": "Москва",
        "projects": [project],
    }
    defaults.update(overrides)
    return FPGOrganization(**defaults)


class TestBuildProjectContext:
    def test_contains_org_info(self):
        org = _make_organization()
        ctx = FPGPipeline._build_project_context(org)
        assert "Test Org" in ctx
        assert "7701234567" in ctx
        assert "Москва" in ctx

    def test_contains_project_titles(self):
        org = _make_organization()
        ctx = FPGPipeline._build_project_context(org)
        assert "Помощь пожилым людям" in ctx

    def test_contains_grant_direction(self):
        org = _make_organization()
        ctx = FPGPipeline._build_project_context(org)
        assert "Социальное обслуживание" in ctx

    def test_winner_status(self):
        org = _make_organization()
        ctx = FPGPipeline._build_project_context(org)
        assert "победитель" in ctx

    def test_elderly_mention(self):
        org = _make_organization()
        ctx = FPGPipeline._build_project_context(org)
        assert "старшего возраста" in ctx


class TestPipelineAnalyze:
    @pytest.mark.asyncio
    async def test_analyze_only(self, mock_core_client, mock_dadata_client):
        pipeline = FPGPipeline(
            core_client=mock_core_client,
            dadata_client=mock_dadata_client,
        )
        stats = await pipeline.analyze_only(FIXTURE_PATH)

        assert stats.total_input == 8
        assert stats.after_direction == 7
        assert stats.after_elderly > 0
        assert stats.unique_organizations > 0

    @pytest.mark.asyncio
    async def test_analyze_summary(self, mock_core_client, mock_dadata_client):
        pipeline = FPGPipeline(
            core_client=mock_core_client,
            dadata_client=mock_dadata_client,
        )
        stats = await pipeline.analyze_only(FIXTURE_PATH)
        summary = stats.summary()
        assert "Total projects" in summary
        assert "Unique organizations" in summary


class TestPipelineDryRun:
    @pytest.mark.asyncio
    async def test_dry_run_returns_report(self, mock_core_client, mock_dadata_client):
        pipeline = FPGPipeline(
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
    async def test_dry_run_report_summary(self, mock_core_client, mock_dadata_client):
        pipeline = FPGPipeline(
            core_client=mock_core_client,
            dadata_client=mock_dadata_client,
            delay_between_orgs=0,
        )
        report = await pipeline.run(
            xlsx_path=FIXTURE_PATH,
            limit=2,
            dry_run=True,
        )

        summary = report.summary()
        assert "FPG Pipeline Report" in summary

    @pytest.mark.asyncio
    async def test_report_to_dict(self, mock_core_client, mock_dadata_client):
        pipeline = FPGPipeline(
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
        """In mock mode (no Core URL), orgs are 'created' locally."""
        pipeline = FPGPipeline(
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


class TestCoreLookup:
    @pytest.mark.asyncio
    async def test_lookup_returns_none_in_mock(self):
        client = NavigatorCoreClient(base_url="", api_token="")
        result = await client.lookup_organization(inn="7701234567")
        assert result is None

    @pytest.mark.asyncio
    async def test_lookup_empty_params(self):
        client = NavigatorCoreClient(base_url="", api_token="")
        result = await client.lookup_organization()
        assert result is None


class TestPipelineMatchedOrg:
    @pytest.mark.asyncio
    async def test_matched_org_gets_updated(self):
        existing = {
            "organizer_id": "org-99",
            "title": "Existing FPG Org",
            "description": "Old desc",
            "ai_metadata": {
                "decision": "accepted",
                "ai_confidence_score": 0.9,
                "ai_source_trace": [],
            },
        }

        mock_core = AsyncMock()
        mock_core.lookup_organization = AsyncMock(return_value=existing)
        mock_core.import_organizer = AsyncMock(return_value={"organizer_id": "org-99"})

        pipeline = FPGPipeline(
            core_client=mock_core,
            dadata_client=DadataClient(api_key=""),
            delay_between_orgs=0,
        )

        org = _make_organization()
        result = await pipeline._process_organization(org, dry_run=False)

        assert result.action == "matched"
        assert result.core_organizer_id == "org-99"

        mock_core.import_organizer.assert_called_once()
        update_payload = mock_core.import_organizer.call_args[0][0]
        assert "ФПГ" in update_payload["description"]
        trace_kinds = [t["source_kind"] for t in update_payload["ai_metadata"]["ai_source_trace"]]
        assert "registry_fpg" in trace_kinds
