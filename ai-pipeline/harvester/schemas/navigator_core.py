"""
Payloads for Navigator Core Internal API (POST /api/internal/import/organizer).
Strictly aligned with Navigator_Core_Model_and_API.md.
"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class AiDecision(str, Enum):
    accepted = "accepted"
    rejected = "rejected"


class VenuePayload(BaseModel):
    address_raw: str
    fias_id: Optional[str] = None
    geo_lat: Optional[float] = None
    geo_lon: Optional[float] = None
    is_headquarters: bool = False


class AiMetadata(BaseModel):
    decision: AiDecision
    ai_confidence_score: float = Field(ge=0.0, le=1.0)
    works_with_elderly: bool
    ai_explanation: Optional[str] = None
    ai_source_trace: Optional[dict] = None


class ClassificationPayload(BaseModel):
    """Codes from seeders. Use code (string), not id (int), for env stability."""

    thematic_category_codes: list[str] = []
    service_codes: list[str] = []
    organization_type_codes: list[str] = []
    specialist_profile_codes: list[str] = []
    ownership_type_code: Optional[str] = None
    coverage_level_id: Optional[int] = None


class OrganizationImportPayload(BaseModel):
    """Matches POST /api/internal/import/organizer."""

    source_reference: str
    entity_type: str = "Organization"
    title: str
    description: Optional[str] = None
    inn: Optional[str] = Field(None, max_length=12)
    ogrn: Optional[str] = Field(None, max_length=15)
    ai_metadata: AiMetadata
    classification: ClassificationPayload
    venues: list[VenuePayload] = []
