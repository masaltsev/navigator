"""
CSS-based extraction strategy — 0 LLM tokens.

Uses Crawl4AI's JsonCssExtractionStrategy with pre-built templates
for known site layouts (KCSON on socinfo.ru, gov35.ru, etc.).

Templates are JSON files in schemas/css_templates/ with the structure:
{
    "name": "kcson_socinfo",
    "baseSelector": "div.main-content",
    "fields": [
        {"name": "title", "selector": "h1.page-title", "type": "text"},
        {"name": "phones", "selector": "a[href^='tel:']", "type": "text", "multiple": true},
        ...
    ]
}

When a source has parse_profile_config.css_template matching a template name,
StrategyRouter uses CSS extraction instead of LLM. This saves ~$0.0006/URL
and runs 10x faster.
"""

import json
import logging
from pathlib import Path
from typing import Optional

from crawl4ai import CrawlerRunConfig, JsonCssExtractionStrategy, CacheMode

logger = logging.getLogger(__name__)

_HARVESTER_ROOT = Path(__file__).resolve().parent.parent
CSS_TEMPLATES_DIR = _HARVESTER_ROOT / "schemas" / "css_templates"


class CssTemplateRegistry:
    """
    Registry of CSS extraction templates.

    Loads JSON templates from schemas/css_templates/ at init time.
    Provides lookup by template name and raw schema access.
    """

    def __init__(self, templates_dir: Optional[Path] = None):
        self._dir = templates_dir or CSS_TEMPLATES_DIR
        self._templates: dict[str, dict] = {}
        self._load_templates()

    def _load_templates(self) -> None:
        if not self._dir.is_dir():
            logger.info("CSS templates directory not found: %s", self._dir)
            return

        for path in self._dir.glob("*.json"):
            try:
                with open(path, encoding="utf-8") as f:
                    template = json.load(f)
                name = template.get("name", path.stem)
                self._templates[name] = template
                logger.info("Loaded CSS template: %s (%s)", name, path.name)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Failed to load CSS template %s: %s", path, e)

    @property
    def available_templates(self) -> list[str]:
        return list(self._templates.keys())

    def has_template(self, name: str) -> bool:
        return name in self._templates

    def get_template(self, name: str) -> Optional[dict]:
        return self._templates.get(name)

    def build_extraction_config(self, template_name: str) -> Optional[CrawlerRunConfig]:
        """
        Build a CrawlerRunConfig with JsonCssExtractionStrategy for the given template.

        Returns None if template not found.
        """
        template = self._templates.get(template_name)
        if not template:
            return None

        strategy = JsonCssExtractionStrategy(schema=template)

        return CrawlerRunConfig(
            extraction_strategy=strategy,
            word_count_threshold=0,
            page_timeout=30000,
            wait_until="domcontentloaded",
            delay_before_return_html=2.0,
            magic=True,
            simulate_user=True,
            cache_mode=CacheMode.BYPASS,
        )


_registry: Optional[CssTemplateRegistry] = None


def get_css_registry() -> CssTemplateRegistry:
    """Singleton access to the CSS template registry."""
    global _registry
    if _registry is None:
        _registry = CssTemplateRegistry()
    return _registry
