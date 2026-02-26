"""Tests for Silver Age pipeline (grouping, pipeline logic, context builders)."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from aggregators.silverage.models import (
    SilverAgeEvent,
    SilverAgeOrganization,
    SilverAgePractice,
)
from aggregators.silverage.silverage_pipeline import (
    OrgResult,
    PipelineReport,
    SilverAgePipeline,
    group_practices_by_org,
)


def _make_practice(
    slug: str = "test",
    title: str = "Test Practice",
    org_name: str = "Org A",
    org_email: str = "",
    org_website: str | None = None,
    region: str = "Москва",
    full_description: str = "Practice description",
    categories: list[str] | None = None,
) -> SilverAgePractice:
    return SilverAgePractice(
        slug=slug,
        title=title,
        org_name=org_name,
        org_email=org_email,
        org_website=org_website,
        region=region,
        full_description=full_description,
        categories=categories or [],
        page_url=f"https://silveragemap.ru/poisk-proekta/{slug}/",
    )


class TestGroupPracticesByOrg:
    def test_groups_by_org_name(self):
        practices = [
            _make_practice(slug="p1", org_name="Org A"),
            _make_practice(slug="p2", org_name="Org B"),
            _make_practice(slug="p3", org_name="Org A"),
        ]
        orgs = group_practices_by_org(practices)
        assert len(orgs) == 2

        org_a = next(o for o in orgs if o.name == "Org A")
        assert org_a.practice_count == 2

        org_b = next(o for o in orgs if o.name == "Org B")
        assert org_b.practice_count == 1

    def test_case_insensitive_grouping(self):
        practices = [
            _make_practice(slug="p1", org_name="Org Alpha"),
            _make_practice(slug="p2", org_name="org alpha"),
        ]
        orgs = group_practices_by_org(practices)
        assert len(orgs) == 1
        assert orgs[0].practice_count == 2

    def test_falls_back_to_title_when_no_org_name(self):
        practices = [
            _make_practice(slug="p1", org_name="", title="Practice Title"),
        ]
        orgs = group_practices_by_org(practices)
        assert len(orgs) == 1
        assert orgs[0].name == "Practice Title"

    def test_sorted_by_practice_count(self):
        practices = [
            _make_practice(slug="p1", org_name="Small Org"),
            _make_practice(slug="p2", org_name="Big Org"),
            _make_practice(slug="p3", org_name="Big Org"),
            _make_practice(slug="p4", org_name="Big Org"),
        ]
        orgs = group_practices_by_org(practices)
        assert orgs[0].name == "Big Org"
        assert orgs[0].practice_count == 3

    def test_preserves_contact_info(self):
        practices = [
            _make_practice(
                slug="p1",
                org_name="Org With Contacts",
                org_email="test@example.com",
                org_website="https://example.com",
            ),
        ]
        orgs = group_practices_by_org(practices)
        assert orgs[0].email == "test@example.com"
        assert orgs[0].website == "https://example.com"


class TestPipelineReport:
    def test_summary(self):
        report = PipelineReport(
            total_practices=100,
            unique_organizations=50,
            total_events=20,
            org_results=[
                OrgResult(name="A", region="X", practice_count=1, action="created"),
                OrgResult(name="B", region="Y", practice_count=2, action="matched"),
                OrgResult(name="C", region="Z", practice_count=1, action="error", error="fail"),
            ],
        )
        assert report.orgs_created == 1
        assert report.orgs_matched == 1
        assert report.orgs_errors == 1
        summary = report.summary()
        assert "100" in summary
        assert "50" in summary

    def test_to_dict(self):
        report = PipelineReport(
            total_practices=10,
            unique_organizations=5,
            total_events=3,
        )
        d = report.to_dict()
        assert d["total_practices"] == 10
        assert d["unique_organizations"] == 5
        assert d["total_events"] == 3


class TestBuildPracticeContext:
    def test_contains_org_name_and_region(self):
        org = SilverAgeOrganization(
            name="АНО Помощь",
            region="Москва",
            practices=[_make_practice(title="Помощь дома")],
        )
        ctx = SilverAgePipeline._build_practice_context(org)
        assert "АНО Помощь" in ctx
        assert "Москва" in ctx

    def test_contains_practice_titles(self):
        org = SilverAgeOrganization(
            name="Test",
            region="Москва",
            practices=[
                _make_practice(slug="p1", title="Йога для старших"),
                _make_practice(slug="p2", title="Компьютерная грамотность"),
            ],
        )
        ctx = SilverAgePipeline._build_practice_context(org)
        assert "Йога для старших" in ctx
        assert "Компьютерная грамотность" in ctx

    def test_contains_categories(self):
        org = SilverAgeOrganization(
            name="Test",
            practices=[
                _make_practice(categories=["Здоровье", "Активное долголетие"]),
            ],
        )
        ctx = SilverAgePipeline._build_practice_context(org)
        assert "Здоровье" in ctx
        assert "Активное долголетие" in ctx

    def test_limits_practices_to_five(self):
        practices = [_make_practice(slug=f"p{i}", title=f"Practice {i}") for i in range(10)]
        org = SilverAgeOrganization(name="Big Org", practices=practices)
        ctx = SilverAgePipeline._build_practice_context(org)
        assert "Practice 0" in ctx
        assert "Practice 4" in ctx
        assert "Practice 5" not in ctx

    def test_elderly_mention(self):
        org = SilverAgeOrganization(
            name="Test",
            practices=[_make_practice()],
        )
        ctx = SilverAgePipeline._build_practice_context(org)
        assert "старшего возраста" in ctx


class TestPipelineDryRun:
    @pytest.mark.asyncio
    async def test_dry_run_does_not_call_core(self):
        mock_core = AsyncMock()
        mock_core.import_organizer = AsyncMock()
        mock_core.import_event = AsyncMock()
        mock_dadata = AsyncMock()

        pipeline = SilverAgePipeline(
            core_client=mock_core,
            dadata_client=mock_dadata,
            scrape_delay=0,
            process_delay=0,
        )

        org = SilverAgeOrganization(
            name="Test Org",
            region="Moscow",
            practices=[_make_practice()],
        )
        result = await pipeline._process_organization(org, dry_run=True)

        assert result.action == "dry_run"
        mock_core.import_organizer.assert_not_called()

    @pytest.mark.asyncio
    async def test_dry_run_event(self):
        mock_core = AsyncMock()
        pipeline = SilverAgePipeline(
            core_client=mock_core,
            scrape_delay=0,
            process_delay=0,
        )

        event = SilverAgeEvent(
            slug="test-event",
            title="Test Event",
            date_text="1 марта",
            location="Онлайн",
            page_url="https://silveragemap.ru/meropriyatiya/test-event/",
        )
        result = await pipeline._process_event(event, dry_run=True)
        assert result.action == "dry_run"
        mock_core.import_event.assert_not_called()


class TestPipelineCreateMinimal:
    @pytest.mark.asyncio
    async def test_creates_minimal_org_when_no_enrichment(self):
        mock_core = AsyncMock()
        mock_core.import_organizer = AsyncMock(return_value={"organizer_id": "123"})
        mock_core.lookup_organization = AsyncMock(return_value=None)

        mock_dadata = AsyncMock()
        mock_dadata.suggest_party = AsyncMock(return_value=[])
        mock_dadata.geocode = AsyncMock(return_value=MagicMock(
            fias_id="", fias_level="", city_fias_id="",
            region_iso="", region_code="", kladr_id="",
            geo_lat="", geo_lon="",
        ))

        pipeline = SilverAgePipeline(
            core_client=mock_core,
            dadata_client=mock_dadata,
            scrape_delay=0,
            process_delay=0,
        )
        pipeline._enrichment_pipeline = None

        org = SilverAgeOrganization(
            name="Test Org Without Website",
            region="Тульская область",
            practices=[_make_practice(title="Practice 1")],
        )
        result = await pipeline._process_organization(org, dry_run=False)

        assert result.action == "created_minimal"
        assert result.core_organizer_id == "123"
        mock_core.import_organizer.assert_called_once()

        payload = mock_core.import_organizer.call_args[0][0]
        assert "silverage_org_" in payload["source_reference"]
        assert payload["ai_metadata"]["works_with_elderly"] is True
        assert "platform_silverage" in payload["ai_metadata"]["ai_source_trace"][0]["source_kind"]

    @pytest.mark.asyncio
    async def test_error_handling(self):
        mock_core = AsyncMock()
        mock_core.lookup_organization = AsyncMock(return_value=None)

        mock_dadata = AsyncMock()
        mock_dadata.suggest_party = AsyncMock(side_effect=Exception("API failure"))

        pipeline = SilverAgePipeline(
            core_client=mock_core,
            dadata_client=mock_dadata,
            scrape_delay=0,
            process_delay=0,
        )

        org = SilverAgeOrganization(
            name="Failing Org",
            practices=[_make_practice()],
        )
        result = await pipeline._process_organization(org, dry_run=False)

        assert result.action == "error"
        assert "API failure" in result.error


class TestPipelineMatchedOrg:
    @pytest.mark.asyncio
    async def test_matched_org_gets_updated(self):
        existing = {
            "organizer_id": "org-42",
            "title": "Existing Org",
            "description": "Old description",
            "ai_metadata": {
                "decision": "accepted",
                "ai_confidence_score": 0.9,
                "ai_source_trace": [],
            },
        }

        mock_core = AsyncMock()
        mock_core.lookup_organization = AsyncMock(return_value=existing)
        mock_core.import_organizer = AsyncMock(return_value={"organizer_id": "org-42"})

        mock_dadata = AsyncMock()
        mock_dadata.suggest_party = AsyncMock(return_value=[
            MagicMock(inn="7701234567"),
        ])

        pipeline = SilverAgePipeline(
            core_client=mock_core,
            dadata_client=mock_dadata,
            scrape_delay=0,
            process_delay=0,
        )

        org = SilverAgeOrganization(
            name="Existing Org",
            region="Москва",
            practices=[_make_practice(title="Yoga for Seniors")],
        )
        result = await pipeline._process_organization(org, dry_run=False)

        assert result.action == "matched"
        assert result.core_organizer_id == "org-42"

        mock_core.import_organizer.assert_called_once()
        update_payload = mock_core.import_organizer.call_args[0][0]
        assert "silveragemap.ru" in update_payload["description"]
        trace_kinds = [t["source_kind"] for t in update_payload["ai_metadata"]["ai_source_trace"]]
        assert "platform_silverage" in trace_kinds
