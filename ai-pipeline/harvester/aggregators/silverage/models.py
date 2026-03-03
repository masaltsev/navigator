"""Models for silveragemap.ru data (Silver Age Alliance / Coalition «Zabota Ryadom»).

Two data sources:
  1. Practice database (~1051 practices, paginated 65 pages)
     URL pattern: /poisk-proekta/{slug}/
  2. Events list (~20 events)
     URL pattern: /meropriyatiya/{slug}/

All content is elderly-relevant by definition.
"""

from typing import Optional

from pydantic import BaseModel, Field


class SilverAgePractice(BaseModel):
    """A practice (проект/практика) from the Silver Age database."""

    slug: str = Field(description="URL slug, e.g. 'kulinarnaya-studiya-vkus-zhizni'")
    title: str
    short_description: str = ""
    full_description: str = ""
    region: str = ""
    categories: list[str] = Field(default_factory=list)
    dates: str = ""
    page_url: str = ""

    org_name: str = ""
    org_description: str = ""
    org_email: str = ""
    org_phone: str = ""
    org_website: Optional[str] = None
    org_vk: Optional[str] = None
    org_social_links: list[str] = Field(default_factory=list)

    @property
    def source_reference(self) -> str:
        return f"silverage_practice_{self.slug}"


class SilverAgeEvent(BaseModel):
    """An event from the Silver Age events page."""

    slug: str = Field(description="URL slug")
    title: str
    date_text: str = ""
    location: str = ""
    description: str = ""
    category: str = ""
    page_url: str = ""
    registration_url: Optional[str] = None

    @property
    def is_online(self) -> bool:
        return "онлайн" in self.location.lower() if self.location else False

    @property
    def source_reference(self) -> str:
        return f"silverage_event_{self.slug}"


class SilverAgeOrganization(BaseModel):
    """Organization extracted from one or more Silver Age practices."""

    name: str
    description: str = ""
    region: str = ""
    email: str = ""
    phone: str = ""
    website: Optional[str] = None
    vk_url: Optional[str] = None
    social_links: list[str] = Field(default_factory=list)
    practices: list[SilverAgePractice] = Field(default_factory=list)

    @property
    def source_reference(self) -> str:
        slug = self.name.lower().replace(" ", "_")[:40]
        return f"silverage_org_{slug}"

    @property
    def practice_count(self) -> int:
        return len(self.practices)

    @property
    def all_categories(self) -> set[str]:
        cats: set[str] = set()
        for p in self.practices:
            cats.update(p.categories)
        return cats

    @property
    def best_description(self) -> str:
        """Longest description from org info or practice descriptions."""
        candidates = [self.description]
        candidates.extend(p.full_description for p in self.practices)
        return max(candidates, key=len) if candidates else ""
