"""
Intermediate model: what the LLM extracts from HTML.
Mapping to seeder codes is done in classifier.py (Sprint 2), not by the LLM.
"""

from pydantic import BaseModel, Field


class RawOrganizationData(BaseModel):
    """Result of LLM extraction. Free-form fields; classifier maps to codes."""

    title: str = Field(..., description="Полное название организации")
    short_description: str = Field(default="", description="Краткое описание (2-3 предложения)")
    full_description: str = Field(default="", description="Полное описание деятельности")
    services_mentioned: list[str] = Field(default=[], description="Упомянутые услуги и сервисы")
    target_audiences: list[str] = Field(default=[], description="Целевые аудитории")
    specialist_types: list[str] = Field(default=[], description="Типы специалистов")
    phones: list[str] = Field(default=[], description="Телефоны")
    emails: list[str] = Field(default=[], description="Email-адреса")
    addresses: list[str] = Field(default=[], description="Полные адреса (город, улица, дом)")
    working_hours: str = Field(default="", description="Режим работы")
    inn: str = Field(default="", description="ИНН (10 или 12 цифр)")
    ogrn: str = Field(default="", description="ОГРН (13 или 15 цифр)")
    organization_type_hints: list[str] = Field(
        default=[],
        description="Тип: КЦСОН, поликлиника, фонд, НКО...",
    )
    works_with_elderly_evidence: str = Field(
        default="",
        description="Цитата/факт подтверждающий работу с пожилыми",
    )
    events_found: list[dict] = Field(
        default=[],
        description="Мероприятия: название, дата, описание, периодичность",
    )
