"""
Unit tests for field protection: null-safety, dadata merge, content hash.
"""

from dataclasses import dataclass, field
from typing import Optional

import pytest

from enrichment.dadata_client import GeocodingResult
from enrichment.dadata_merge import merge_dadata_into_payload
from processors.organization_processor import _compute_content_hash, to_core_import_payload
from prompts.schemas import (
    AIConfidenceMetadata,
    ExtractedContact,
    ExtractedVenue,
    OrganizationClassification,
    OrganizationOutput,
)


def _make_org(**overrides) -> OrganizationOutput:
    defaults = dict(
        source_reference="https://example.com",
        title="Тестовая организация",
        description="Описание организации",
        ai_metadata=AIConfidenceMetadata(
            works_with_elderly=True,
            ai_confidence_score=0.90,
            ai_explanation="Тестовое обоснование",
            decision="accepted",
        ),
        classification=OrganizationClassification(
            organization_type_codes=["141"],
            ownership_type_code="154",
            thematic_category_codes=["7"],
            service_codes=["70"],
            specialist_profile_codes=[],
        ),
        venues=[],
        contacts=ExtractedContact(),
        target_audience=["elderly"],
    )
    defaults.update(overrides)
    return OrganizationOutput(**defaults)


class TestNullSafety:
    """Empty inn/ogrn/short_title should not be sent in payload."""

    def test_null_inn_not_in_payload(self):
        org = _make_org(inn=None)
        payload = to_core_import_payload(org)
        assert "inn" not in payload

    def test_null_ogrn_not_in_payload(self):
        org = _make_org(ogrn=None)
        payload = to_core_import_payload(org)
        assert "ogrn" not in payload

    def test_null_short_title_not_in_payload(self):
        org = _make_org(short_title=None)
        payload = to_core_import_payload(org)
        assert "short_title" not in payload

    def test_empty_string_inn_not_in_payload(self):
        org = _make_org(inn="")
        payload = to_core_import_payload(org)
        assert "inn" not in payload

    def test_present_inn_in_payload(self):
        org = _make_org(inn="7700000001")
        payload = to_core_import_payload(org)
        assert payload["inn"] == "7700000001"

    def test_present_ogrn_in_payload(self):
        org = _make_org(ogrn="1234567890123")
        payload = to_core_import_payload(org)
        assert payload["ogrn"] == "1234567890123"

    def test_present_short_title_in_payload(self):
        org = _make_org(short_title="Краткое")
        payload = to_core_import_payload(org)
        assert payload["short_title"] == "Краткое"


class TestContentHash:
    """Content hash computation and stability."""

    def test_content_hash_present(self):
        org = _make_org()
        payload = to_core_import_payload(org)
        assert "content_hash" in payload
        assert len(payload["content_hash"]) == 16

    def test_content_hash_stable(self):
        org = _make_org()
        p1 = to_core_import_payload(org)
        p2 = to_core_import_payload(org)
        assert p1["content_hash"] == p2["content_hash"]

    def test_content_hash_changes_with_title(self):
        org1 = _make_org(title="Название A")
        org2 = _make_org(title="Название B")
        p1 = to_core_import_payload(org1)
        p2 = to_core_import_payload(org2)
        assert p1["content_hash"] != p2["content_hash"]

    def test_content_hash_changes_with_inn(self):
        org1 = _make_org(inn="1111111111")
        org2 = _make_org(inn="2222222222")
        p1 = to_core_import_payload(org1)
        p2 = to_core_import_payload(org2)
        assert p1["content_hash"] != p2["content_hash"]

    def test_compute_content_hash_deterministic(self):
        payload = {"title": "Test", "description": "Desc", "inn": "123", "classification": {}}
        h1 = _compute_content_hash(payload)
        h2 = _compute_content_hash(payload)
        assert h1 == h2


@dataclass
class FakePartyResult:
    """Minimal party result for testing merge logic."""

    found: bool = True
    inn: Optional[str] = None
    ogrn: Optional[str] = None
    name_full: Optional[str] = None
    name_short: Optional[str] = None
    address: Optional[str] = None
    address_unrestricted: Optional[str] = None
    phones: list = field(default_factory=list)
    emails: list = field(default_factory=list)
    raw_data: Optional[dict] = None

    def to_geocoding_result(self):
        return GeocodingResult(address_raw=self.address or "")


class TestDadataMerge:
    """DaData merge into harvest payload."""

    def test_merge_fills_empty_inn(self):
        payload = {"title": "Test", "contacts": {"phones": [], "emails": []}}
        party = FakePartyResult(inn="7700000001", ogrn="1234567890123")
        verified = merge_dadata_into_payload(payload, party)

        assert payload["inn"] == "7700000001"
        assert payload["ogrn"] == "1234567890123"
        assert verified["inn"] == "dadata"
        assert verified["ogrn"] == "dadata"

    def test_merge_does_not_overwrite_existing_inn(self):
        payload = {"title": "Test", "inn": "EXISTING", "contacts": {"phones": [], "emails": []}}
        party = FakePartyResult(inn="7700000001")
        merge_dadata_into_payload(payload, party)

        assert payload["inn"] == "EXISTING"

    def test_merge_overwrites_title(self):
        payload = {"title": "LLM Title", "contacts": {"phones": [], "emails": []}}
        party = FakePartyResult(inn="123", name_full="DaData Full Name", name_short="DaData Short")
        verified = merge_dadata_into_payload(payload, party)

        assert payload["title"] == "DaData Full Name"
        assert payload["short_title"] == "DaData Short"
        assert verified["title"] == "dadata"

    def test_merge_appends_contacts(self):
        payload = {
            "title": "Test",
            "contacts": {"phones": ["+71111111111"], "emails": ["a@b.com"]},
        }
        party = FakePartyResult(
            inn="123",
            phones=["+72222222222", "+71111111111"],
            emails=["c@d.com"],
        )
        merge_dadata_into_payload(payload, party)

        assert "+71111111111" in payload["contacts"]["phones"]
        assert "+72222222222" in payload["contacts"]["phones"]
        assert "a@b.com" in payload["contacts"]["emails"]
        assert "c@d.com" in payload["contacts"]["emails"]

    def test_merge_returns_empty_for_empty_party(self):
        payload = {"title": "Test"}
        party = FakePartyResult(found=True, inn=None, address=None)
        verified = merge_dadata_into_payload(payload, party)

        assert verified == {}

    def test_merge_appends_registry_venue(self):
        payload = {"title": "Test", "venues": [], "contacts": {"phones": [], "emails": []}}
        party = FakePartyResult(
            inn="123",
            address="г. Москва, ул. Тестовая, 1",
            raw_data={"address": {"data": {}}},
        )
        merge_dadata_into_payload(payload, party)

        assert len(payload["venues"]) == 1
        assert payload["venues"][0]["address_comment"] == "адрес из реестра Dadata"

    def test_verified_fields_dict_returned(self):
        payload = {"title": "Test", "contacts": {"phones": [], "emails": []}}
        party = FakePartyResult(
            inn="7700000001",
            ogrn="1234567890123",
            name_full="Official Name",
        )
        verified = merge_dadata_into_payload(payload, party)

        assert isinstance(verified, dict)
        assert verified["inn"] == "dadata"
        assert verified["ogrn"] == "dadata"
        assert verified["title"] == "dadata"
