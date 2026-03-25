"""
Shared DaData merge logic for enriching harvest payloads with party data.

Used by:
  - EnrichmentPipeline (broken URL / missing source flows)
  - run_organization_harvest (nightly crawl)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

import structlog

if TYPE_CHECKING:
    from enrichment.dadata_client import PartyResult

logger = structlog.get_logger(__name__)


def merge_dadata_into_payload(
    harvest_output: dict,
    party: "PartyResult",
    *,
    overwrite_title: bool = True,
) -> dict[str, str]:
    """Merge DaData party data (INN, OGRN, name, address, contacts) into harvest payload.

    DaData is the source of truth for organization name when we have a party match.

    Returns a dict of field names verified by DaData (for verified_fields tracking).
    """
    if not harvest_output or not party:
        return {}

    if not getattr(party, "inn", None) and not getattr(party, "address", None):
        return {}

    verified: dict[str, str] = {}

    if not harvest_output.get("inn") and party.inn:
        harvest_output["inn"] = party.inn
    if party.inn:
        verified["inn"] = "dadata"

    if not harvest_output.get("ogrn") and party.ogrn:
        harvest_output["ogrn"] = party.ogrn
    if party.ogrn:
        verified["ogrn"] = "dadata"

    if overwrite_title:
        name_full = (getattr(party, "name_full", None) or "").strip()
        name_short = (getattr(party, "name_short", None) or "").strip()
        dadata_title = name_full or name_short
        if dadata_title:
            harvest_output["title"] = dadata_title
            if name_short and name_short != name_full:
                harvest_output["short_title"] = name_short
            verified["title"] = "dadata"
            verified["short_title"] = "dadata"
            logger.debug("dadata_merge_title", title=dadata_title[:60])

    contacts = harvest_output.get("contacts") or {}
    phones = list(contacts.get("phones") or [])
    emails = list(contacts.get("emails") or [])
    for p in getattr(party, "phones", []) or []:
        if p and p not in phones:
            phones.append(p)
    for e in getattr(party, "emails", []) or []:
        if e and e not in emails:
            emails.append(e)
    harvest_output["contacts"] = {"phones": phones, "emails": emails}

    _append_registry_venue(harvest_output, party)

    return verified


def _append_registry_venue(harvest_output: dict, party: "PartyResult") -> None:
    """Append the registry address from DaData party as an additional venue."""
    if not party.address:
        return
    try:
        geo = party.to_geocoding_result()
        venue_data: dict = {
            "address_raw": geo.address_raw,
            "address_comment": "адрес из реестра Dadata",
        }
        if geo.fias_id:
            venue_data["fias_id"] = geo.fias_id
        if geo.fias_level:
            venue_data["fias_level"] = geo.fias_level
        if geo.city_fias_id:
            venue_data["city_fias_id"] = geo.city_fias_id
        if geo.region_iso:
            venue_data["region_iso"] = geo.region_iso
        if geo.region_code:
            venue_data["region_code"] = geo.region_code
        if geo.kladr_id:
            venue_data["kladr_id"] = geo.kladr_id
        if geo.geo_lat is not None and geo.geo_lon is not None:
            venue_data["geo_lat"] = geo.geo_lat
            venue_data["geo_lon"] = geo.geo_lon
        venues = list(harvest_output.get("venues") or [])
        venues.append(venue_data)
        harvest_output["venues"] = venues
        logger.info(
            "dadata_merge_venue",
            org=harvest_output.get("title", "")[:40],
            inn=harvest_output.get("inn"),
            venue_added=geo.address_raw[:60],
        )
    except Exception as e:
        logger.warning("dadata_merge_venue_error", error=str(e))
