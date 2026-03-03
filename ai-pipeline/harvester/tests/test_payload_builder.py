"""
Unit tests for to_core_import_payload() conversion.

Verifies that OrganizationOutput → Core API payload is correct,
including venue enrichment with Dadata geocoding results.
"""

import pytest

from enrichment.dadata_client import GeocodingResult
from processors.organization_processor import to_core_import_payload
from prompts.schemas import (
    AIConfidenceMetadata,
    ExtractedContact,
    ExtractedVenue,
    OrganizationClassification,
    OrganizationOutput,
    TaxonomySuggestion,
)


def _make_org_output(**overrides) -> OrganizationOutput:
    """Minimal OrganizationOutput for testing."""
    defaults = dict(
        source_reference="https://example.com",
        title="КЦСОН г. Вологды",
        short_title="КЦСОН Вологда",
        description="Центр социального обслуживания населения",
        inn="3525155950",
        ogrn="1043500037498",
        ai_metadata=AIConfidenceMetadata(
            works_with_elderly=True,
            ai_confidence_score=0.95,
            ai_explanation="КЦСОН с гериатрическими программами",
            decision="accepted",
        ),
        classification=OrganizationClassification(
            organization_type_codes=["141"],
            ownership_type_code="154",
            thematic_category_codes=["7", "24"],
            service_codes=["70", "75"],
            specialist_profile_codes=["143"],
        ),
        venues=[
            ExtractedVenue(
                address_raw="г. Вологда, ул. Козлёнская, д. 35",
                address_comment="3 этаж",
            ),
        ],
        contacts=ExtractedContact(
            phones=["+78172721344"],
            emails=["kcson@gov35.ru"],
            website_urls=["https://kcson-vologda.gov35.ru"],
            vk_url="https://vk.com/kcson_vologda",
            telegram_url="https://t.me/kcson_vologda",
        ),
        target_audience=["elderly", "relatives"],
    )
    defaults.update(overrides)
    return OrganizationOutput(**defaults)


class TestBasicPayload:
    def test_required_fields_present(self):
        org = _make_org_output()
        payload = to_core_import_payload(org)

        assert payload["source_reference"] == "https://example.com"
        assert payload["entity_type"] == "Organization"
        assert payload["title"] == "КЦСОН г. Вологды"
        assert payload["inn"] == "3525155950"
        assert payload["ogrn"] == "1043500037498"

    def test_ai_metadata(self):
        org = _make_org_output()
        payload = to_core_import_payload(org)

        meta = payload["ai_metadata"]
        assert meta["decision"] == "accepted"
        assert meta["ai_confidence_score"] == pytest.approx(0.95)
        assert meta["works_with_elderly"] is True
        assert "КЦСОН" in meta["ai_explanation"]

    def test_classification_codes(self):
        org = _make_org_output()
        payload = to_core_import_payload(org)

        cls = payload["classification"]
        assert "141" in cls["organization_type_codes"]
        assert cls["ownership_type_code"] == "154"
        assert "7" in cls["thematic_category_codes"]
        assert "70" in cls["service_codes"]

    def test_contacts(self):
        org = _make_org_output()
        payload = to_core_import_payload(org)

        assert "+78172721344" in payload["contacts"]["phones"]
        assert "kcson@gov35.ru" in payload["contacts"]["emails"]
        assert "https://kcson-vologda.gov35.ru" in payload["site_urls"]
        assert payload["vk_group_url"] == "https://vk.com/kcson_vologda"
        assert payload["telegram_url"] == "https://t.me/kcson_vologda"

    def test_target_audience_is_list(self):
        org = _make_org_output()
        payload = to_core_import_payload(org)
        assert isinstance(payload["target_audience"], list)
        assert "elderly" in payload["target_audience"]


class TestVenueWithoutGeo:
    def test_venue_without_enrichment(self):
        org = _make_org_output()
        payload = to_core_import_payload(org)

        assert len(payload["venues"]) == 1
        venue = payload["venues"][0]
        assert venue["address_raw"] == "г. Вологда, ул. Козлёнская, д. 35"
        assert venue["address_comment"] == "3 этаж"
        assert "fias_id" not in venue
        assert "geo_lat" not in venue


class TestVenueWithDadata:
    def test_venue_enriched_with_geo(self):
        org = _make_org_output()
        geo = [
            GeocodingResult(
                address_raw="г. Вологда, ул. Козлёнская, д. 35",
                fias_id="abc-123-fias",
                geo_lat=59.2239,
                geo_lon=39.8842,
            ),
        ]
        payload = to_core_import_payload(org, geo_results=geo)

        venue = payload["venues"][0]
        assert venue["fias_id"] == "abc-123-fias"
        assert venue["geo_lat"] == pytest.approx(59.2239)
        assert venue["geo_lon"] == pytest.approx(39.8842)

    def test_venue_partial_geo(self):
        """Dadata returned result but without coordinates."""
        org = _make_org_output()
        geo = [
            GeocodingResult(
                address_raw="г. Вологда",
                fias_id="fias-no-coords",
            ),
        ]
        payload = to_core_import_payload(org, geo_results=geo)

        venue = payload["venues"][0]
        assert venue["fias_id"] == "fias-no-coords"
        assert "geo_lat" not in venue

    def test_venue_empty_geo_result(self):
        """Dadata returned empty result (no fias_id)."""
        org = _make_org_output()
        geo = [GeocodingResult(address_raw="unknown address")]
        payload = to_core_import_payload(org, geo_results=geo)

        venue = payload["venues"][0]
        assert "fias_id" not in venue

    def test_multiple_venues_partial_geo(self):
        """Two venues, only first one geocoded."""
        org = _make_org_output(
            venues=[
                ExtractedVenue(address_raw="addr1"),
                ExtractedVenue(address_raw="addr2"),
            ]
        )
        geo = [
            GeocodingResult(address_raw="addr1", fias_id="fias-1", geo_lat=55.0, geo_lon=37.0),
        ]
        payload = to_core_import_payload(org, geo_results=geo)

        assert payload["venues"][0]["fias_id"] == "fias-1"
        assert "fias_id" not in payload["venues"][1]


class TestNullableFields:
    def test_no_inn_ogrn(self):
        org = _make_org_output(inn=None, ogrn=None)
        payload = to_core_import_payload(org)
        assert payload["inn"] is None
        assert payload["ogrn"] is None

    def test_no_short_title(self):
        org = _make_org_output(short_title=None)
        payload = to_core_import_payload(org)
        assert payload["short_title"] is None

    def test_empty_venues(self):
        org = _make_org_output(venues=[])
        payload = to_core_import_payload(org)
        assert payload["venues"] == []

    def test_suggested_taxonomy_roundtrip(self):
        suggestion = TaxonomySuggestion(
            target_dictionary="services",
            proposed_name="Школа ухода",
            proposed_description="Обучение навыкам ухода за пожилыми родственниками",
            importance_for_elderly="Помогает родственникам обеспечить качественный уход",
            source_text_fragment="Школа ухода за пожилыми людьми — обучающая программа",
        )
        org = _make_org_output(suggested_taxonomy=[suggestion])
        payload = to_core_import_payload(org)

        assert len(payload["suggested_taxonomy"]) == 1
        s = payload["suggested_taxonomy"][0]
        assert s["target_dictionary"] == "services"
        assert s["proposed_name"] == "Школа ухода"
