"""
Unit tests for enrichment/dadata_client.py.

All tests run without real Dadata API calls — testing mapping logic
and disabled/passthrough mode.
"""

import asyncio

import pytest

from enrichment.dadata_client import (
    DadataClient,
    GeocodingResult,
    PartyResult,
    _pick_city_fias_id,
    _pick_fias_level,
    _pick_kladr_id,
    _pick_region_code,
    _pick_settlement_or_city_fias_id,
    _safe_float,
    _str_or_none,
)


# ---------------------------------------------------------------------------
# DadataClient: disabled / passthrough
# ---------------------------------------------------------------------------


class TestDadataClientDisabled:
    def test_disabled_by_default(self):
        client = DadataClient()
        assert not client.enabled

    def test_disabled_returns_passthrough(self):
        client = DadataClient()
        result = asyncio.run(client.geocode("г. Вологда, ул. Козлёнская, д. 35"))
        assert isinstance(result, GeocodingResult)
        assert result.address_raw == "г. Вологда, ул. Козлёнская, д. 35"
        assert result.fias_id is None
        assert result.geo_lat is None

    def test_metrics_when_disabled(self):
        client = DadataClient()
        metrics = client.get_metrics()
        assert metrics["total_calls"] == 0
        assert metrics["mode"] == "suggest"


class TestDadataClientEnabled:
    def test_enabled_with_key(self):
        client = DadataClient(api_key="test-key")
        assert client.enabled

    def test_suggest_is_default_mode(self):
        client = DadataClient(api_key="test-key", secret_key="test-secret")
        assert client.get_metrics()["mode"] == "suggest"

    def test_clean_mode_opt_in(self):
        client = DadataClient(api_key="k", secret_key="s", use_clean=True)
        assert client.get_metrics()["mode"] == "clean"

    def test_clean_mode_requires_secret(self):
        client = DadataClient(api_key="k", use_clean=True)
        assert client.get_metrics()["mode"] == "suggest"


class TestFindPartyDisabled:
    def test_disabled_returns_empty(self):
        client = DadataClient()
        result = asyncio.run(client.find_party_by_id("1234567890"))
        assert isinstance(result, PartyResult)
        assert not result.found

    def test_empty_inn_returns_empty(self):
        client = DadataClient(api_key="test")
        result = asyncio.run(client.find_party_by_id("  "))
        assert not result.found


# ---------------------------------------------------------------------------
# FIAS ID mapping — mirrors VenueAddressEnricher logic
# ---------------------------------------------------------------------------


class TestPickSettlementOrCityFiasId:
    """fias_id stored in venues = settlement → city → region."""

    def test_prefers_settlement(self):
        data = {
            "settlement_fias_id": "settlement-uuid",
            "city_fias_id": "city-uuid",
            "region_fias_id": "region-uuid",
        }
        assert _pick_settlement_or_city_fias_id(data) == "settlement-uuid"

    def test_falls_back_to_city(self):
        data = {
            "settlement_fias_id": None,
            "city_fias_id": "city-uuid",
            "region_fias_id": "region-uuid",
        }
        assert _pick_settlement_or_city_fias_id(data) == "city-uuid"

    def test_falls_back_to_region(self):
        data = {
            "settlement_fias_id": "",
            "city_fias_id": "",
            "region_fias_id": "region-uuid",
        }
        assert _pick_settlement_or_city_fias_id(data) == "region-uuid"

    def test_all_empty_returns_none(self):
        assert _pick_settlement_or_city_fias_id({}) is None

    def test_empty_strings_treated_as_none(self):
        data = {"settlement_fias_id": "  ", "city_fias_id": "", "region_fias_id": None}
        assert _pick_settlement_or_city_fias_id(data) is None


class TestPickFiasLevel:
    def test_settlement_is_level_6(self):
        assert _pick_fias_level({"settlement_fias_id": "x"}) == "6"

    def test_city_is_level_4(self):
        assert _pick_fias_level({"city_fias_id": "x"}) == "4"

    def test_region_is_level_1(self):
        assert _pick_fias_level({"region_fias_id": "x"}) == "1"

    def test_settlement_takes_priority(self):
        data = {"settlement_fias_id": "s", "city_fias_id": "c", "region_fias_id": "r"}
        assert _pick_fias_level(data) == "6"

    def test_empty_returns_none(self):
        assert _pick_fias_level({}) is None


class TestPickCityFiasId:
    def test_direct_from_data(self):
        assert _pick_city_fias_id({"city_fias_id": "city-uuid"}) == "city-uuid"

    def test_empty_returns_none(self):
        assert _pick_city_fias_id({"city_fias_id": ""}) is None

    def test_missing_returns_none(self):
        assert _pick_city_fias_id({}) is None


class TestPickRegionCode:
    """region_code is used only when region_iso_code is absent (new regions)."""

    def test_returns_none_when_iso_exists(self):
        data = {"region_iso_code": "RU-VLG", "region_fias_id": "r-uuid"}
        assert _pick_region_code(data) is None

    def test_returns_region_fias_id_when_no_iso(self):
        data = {"region_iso_code": None, "region_fias_id": "lnr-uuid"}
        assert _pick_region_code(data) == "lnr-uuid"

    def test_returns_none_when_both_empty(self):
        assert _pick_region_code({}) is None


class TestPickKladrId:
    def test_prefers_house(self):
        data = {"house_kladr_id": "h", "city_kladr_id": "c"}
        assert _pick_kladr_id(data) == "h"

    def test_falls_back_to_city(self):
        data = {"city_kladr_id": "c", "region_kladr_id": "r"}
        assert _pick_kladr_id(data) == "c"

    def test_generic_kladr_id(self):
        data = {"kladr_id": "generic"}
        assert _pick_kladr_id(data) == "generic"


# ---------------------------------------------------------------------------
# Full mapping integration (mapDataToResult via _map_data_to_result)
# ---------------------------------------------------------------------------


class TestMapDataToResult:
    """Test the full mapping pipeline via DadataClient._map_data_to_result."""

    def _map(self, data: dict, address_raw: str = "test") -> GeocodingResult:
        client = DadataClient.__new__(DadataClient)
        return client._map_data_to_result(data, address_raw)

    def test_typical_city_address(self):
        data = {
            "city_fias_id": "city-123",
            "region_fias_id": "region-456",
            "region_iso_code": "RU-VLG",
            "geo_lat": "59.22",
            "geo_lon": "39.88",
            "kladr_id": "35000001000",
        }
        r = self._map(data, "г. Вологда, ул. Козлёнская")
        assert r.fias_id == "city-123"
        assert r.fias_level == "4"
        assert r.city_fias_id == "city-123"
        assert r.region_iso == "RU-VLG"
        assert r.region_code is None  # ISO exists
        assert r.geo_lat == pytest.approx(59.22)

    def test_settlement_address(self):
        data = {
            "settlement_fias_id": "settlement-789",
            "city_fias_id": "city-123",
            "region_fias_id": "region-456",
            "region_iso_code": "RU-KGD",
            "geo_lat": "54.71",
            "geo_lon": "20.51",
        }
        r = self._map(data)
        assert r.fias_id == "settlement-789"
        assert r.fias_level == "6"
        assert r.city_fias_id == "city-123"

    def test_settlement_without_city(self):
        """Settlement (level 6) without city_fias_id: fallback city_fias_id = fias_id."""
        data = {
            "settlement_fias_id": "village-111",
            "city_fias_id": None,
            "region_fias_id": "region-222",
            "region_iso_code": "RU-VLG",
        }
        r = self._map(data)
        assert r.fias_id == "village-111"
        assert r.fias_level == "6"
        assert r.city_fias_id == "village-111"  # fallback

    def test_federal_city_moscow(self):
        """Federal city (RU-MOW) with fias_level=1: city_fias_id = fias_id."""
        data = {
            "region_fias_id": "moscow-region-uuid",
            "region_iso_code": "RU-MOW",
            "geo_lat": "55.75",
            "geo_lon": "37.62",
        }
        r = self._map(data)
        assert r.fias_id == "moscow-region-uuid"
        assert r.fias_level == "1"
        assert r.city_fias_id == "moscow-region-uuid"  # federal city fallback

    def test_federal_city_spb(self):
        data = {
            "region_fias_id": "spb-uuid",
            "region_iso_code": "RU-SPE",
        }
        r = self._map(data)
        assert r.city_fias_id == "spb-uuid"

    def test_new_region_without_iso(self):
        """LNR/DNR/etc: region_iso_code is null, region_code = region_fias_id."""
        data = {
            "region_fias_id": "lnr-uuid",
            "region_iso_code": None,
            "city_fias_id": "luhansk-city-uuid",
            "geo_lat": "48.57",
            "geo_lon": "39.33",
        }
        r = self._map(data)
        assert r.region_iso is None
        assert r.region_code == "lnr-uuid"
        assert r.city_fias_id == "luhansk-city-uuid"

    def test_region_only_no_city(self):
        """Region level only, no city: city_fias_id falls back to fias_id."""
        data = {
            "region_fias_id": "region-uuid",
            "region_iso_code": "RU-AMU",
        }
        r = self._map(data)
        assert r.fias_level == "1"
        assert r.city_fias_id == "region-uuid"  # non-federal region fallback

    def test_empty_data(self):
        r = self._map({}, "some address")
        assert r.fias_id is None
        assert r.city_fias_id is None
        assert r.fias_level is None


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------


class TestSafeFloat:
    def test_none(self):
        assert _safe_float(None) is None

    def test_valid_string(self):
        assert _safe_float("59.2239") == pytest.approx(59.2239)

    def test_valid_float(self):
        assert _safe_float(39.88) == pytest.approx(39.88)

    def test_invalid_string(self):
        assert _safe_float("not-a-number") is None

    def test_empty_string(self):
        assert _safe_float("") is None


class TestStrOrNone:
    def test_normal_string(self):
        assert _str_or_none("hello") == "hello"

    def test_empty_string(self):
        assert _str_or_none("") is None

    def test_whitespace_only(self):
        assert _str_or_none("  ") is None

    def test_none(self):
        assert _str_or_none(None) is None


class TestBatchGeocoding:
    def test_empty_batch(self):
        client = DadataClient()
        results = asyncio.run(client.geocode_batch([]))
        assert results == []

    def test_batch_disabled_passthrough(self):
        client = DadataClient()
        addresses = ["addr1", "addr2", "addr3"]
        results = asyncio.run(client.geocode_batch(addresses))
        assert len(results) == 3
        assert all(r.fias_id is None for r in results)
        assert [r.address_raw for r in results] == addresses
