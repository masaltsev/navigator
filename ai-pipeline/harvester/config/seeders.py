"""
Load Navigator seeders from JSON (exported by Laravel seeders:export-json).
Single source of truth: backend/database/seeders/*. PHP exports → seeders_data/*.json.
"""

import json
from pathlib import Path

from pydantic import BaseModel

SEEDERS_DIR = Path(__file__).resolve().parent.parent / "seeders_data"


class SeederItem(BaseModel):
    id: int | None = None
    code: str
    name: str
    is_active: bool = True
    parent_code: str | None = None  # Only for ThematicCategory


class NavigatorSeeders(BaseModel):
    thematic_categories: list[SeederItem]
    services: list[SeederItem]
    organization_types: list[SeederItem]
    specialist_profiles: list[SeederItem]
    ownership_types: list[SeederItem]

    @property
    def child_categories(self) -> list[SeederItem]:
        """Only child categories (for mapping — not roots 3/4/5)."""
        return [c for c in self.thematic_categories if c.parent_code is not None]


def load_seeders() -> NavigatorSeeders:
    """Load from JSON files in seeders_data/."""
    return NavigatorSeeders(
        thematic_categories=_load("thematic_categories.json"),
        services=_load("services.json"),
        organization_types=_load("organization_types.json"),
        specialist_profiles=_load("specialist_profiles.json"),
        ownership_types=_load("ownership_types.json"),
    )


def _load(filename: str) -> list[SeederItem]:
    path = SEEDERS_DIR / filename
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    return [SeederItem(**item) for item in raw if item.get("is_active", True)]
