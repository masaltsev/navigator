"""Pydantic models for SONKO (Socially Oriented NCOs) registry data.

Source: https://data.economy.gov.ru/analytics/sonko
Download: https://data.economy.gov.ru/files/sonko_organizations.xlsx

XLSX layout (title row 1, headers row 2, data from row 3+, rows 3-20 may be empty):
  Col 0:  ИНН организации
  Col 1:  Наименование организации (полное)
  Col 2:  Наименование организации (сокращенное)
  Col 3:  Адрес регистрации
  Col 4:  ОГРН
  Col 5:  Организационно-правовая форма
  Col 6:  Основной ОКВЭД
  Col 7:  Статус СОНКО
  Col 8:  Статус некоммерческой организации
  Col 9:  Критерий включения в реестр
  Col 10: Наименование органа власти
  Col 11: Дата принятия решения
  Col 12: Дата включения в реестр

One INN may appear in multiple rows (different support episodes).
"""

from typing import Optional

from pydantic import BaseModel, Field, field_validator


class SONKOEntry(BaseModel):
    """Single row from the SONKO registry XLSX."""

    inn: str = Field(description="ИНН организации")
    full_name: str = Field(description="Наименование организации (полное)")
    short_name: Optional[str] = Field(default=None, description="Наименование (сокращенное)")
    address: str = Field(default="", description="Адрес регистрации")
    ogrn: str = Field(default="", description="ОГРН")
    legal_form: Optional[str] = Field(default=None, description="Организационно-правовая форма")
    okved: str = Field(default="", description="Основной ОКВЭД")
    sonko_status: Optional[str] = Field(default=None, description="Статус СОНКО")
    nco_status: Optional[str] = Field(default=None, description="Статус НКО")
    inclusion_criterion: Optional[str] = Field(default=None, description="Критерий включения в реестр")
    authority_name: Optional[str] = Field(default=None, description="Орган власти")
    decision_date: Optional[str] = Field(default=None, description="Дата принятия решения")
    inclusion_date: Optional[str] = Field(default=None, description="Дата включения в реестр")

    @field_validator("inn", "ogrn", "okved", mode="before")
    @classmethod
    def coerce_to_str(cls, v: object) -> str:
        if v is None:
            return ""
        return str(v).strip()

    @field_validator("full_name", "address", mode="before")
    @classmethod
    def strip_str(cls, v: object) -> str:
        if v is None:
            return ""
        return str(v).strip()

    @field_validator("short_name", "legal_form", "sonko_status", "nco_status",
                     "inclusion_criterion", "authority_name", "decision_date",
                     "inclusion_date", mode="before")
    @classmethod
    def optional_strip(cls, v: object) -> Optional[str]:
        if v is None:
            return None
        s = str(v).strip()
        return s if s else None

    @property
    def okved_prefix(self) -> str:
        """First two digits of OKVED code, e.g. '88' from '88.10'."""
        return self.okved.split(".")[0] if self.okved else ""

    @property
    def source_reference(self) -> str:
        return f"sonko_{self.inn}"


class SONKOOrganization(BaseModel):
    """Aggregated organization from one or more SONKO registry entries.

    Since the same INN can appear in multiple rows (different support
    episodes / authorities), we group entries and keep the richest info.
    """

    inn: str
    ogrn: str = ""
    full_name: str
    short_name: Optional[str] = None
    address: str = ""
    okved: str = ""
    legal_form: Optional[str] = None
    entries: list[SONKOEntry] = Field(default_factory=list)

    @property
    def entry_count(self) -> int:
        return len(self.entries)

    @property
    def source_reference(self) -> str:
        return f"sonko_{self.inn}"

    @property
    def okved_prefix(self) -> str:
        return self.okved.split(".")[0] if self.okved else ""

    @property
    def all_statuses(self) -> set[str]:
        return {e.sonko_status for e in self.entries if e.sonko_status}

    @property
    def all_criteria(self) -> set[str]:
        return {e.inclusion_criterion for e in self.entries if e.inclusion_criterion}

    @property
    def all_authorities(self) -> set[str]:
        return {e.authority_name for e in self.entries if e.authority_name}

    @property
    def is_social_service_provider(self) -> bool:
        return any("поставщик социальных услуг" in (e.sonko_status or "").lower()
                    for e in self.entries)

    @property
    def region_from_address(self) -> str:
        """Extract region from the registration address (first comma-separated part)."""
        if not self.address:
            return ""
        parts = self.address.split(",")
        for part in parts:
            clean = part.strip()
            if any(kw in clean.lower() for kw in (
                "область", "край", "республика", "округ",
                "москва", "санкт-петербург", "севастополь",
            )):
                return clean
        return parts[1].strip() if len(parts) > 1 else ""
