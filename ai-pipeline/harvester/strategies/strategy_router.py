"""
Strategy router: choose CSS template (0 tokens) or LLM extraction (DeepSeek).
Regex is always applied as an extra layer for contacts (see regex_strategy).
"""

import json
from pathlib import Path

from crawl4ai import (
    CrawlerRunConfig,
    JsonCssExtractionStrategy,
    LLMExtractionStrategy,
)

from config.llm_config import get_llm_config
from prompts.prompt_registry import get_extraction_prompt
from schemas.extraction import RawOrganizationData

_HARVESTER_ROOT = Path(__file__).resolve().parent.parent
CSS_TEMPLATES_DIR = _HARVESTER_ROOT / "schemas" / "css_templates"


class StrategyRouter:
    """Priority: CSS template (0 tokens) → LLM (DeepSeek)."""

    def __init__(self) -> None:
        self.llm_config: LLMConfig = get_llm_config()
        self._css_cache: dict[str, dict] = {}
        self._load_css_templates()

    def _load_css_templates(self) -> None:
        if not CSS_TEMPLATES_DIR.is_dir():
            return
        for path in CSS_TEMPLATES_DIR.glob("*.json"):
            with open(path, encoding="utf-8") as f:
                self._css_cache[path.stem] = json.load(f)

    def get_extraction_config(
        self,
        source_kind: str,
        parse_profile_config: dict,
    ) -> CrawlerRunConfig:
        css_template = parse_profile_config.get("css_template")

        if css_template and css_template in self._css_cache:
            strategy: JsonCssExtractionStrategy | LLMExtractionStrategy = (
                JsonCssExtractionStrategy(schema=self._css_cache[css_template])
            )
        else:
            instruction = get_extraction_prompt(source_kind, parse_profile_config)
            strategy = LLMExtractionStrategy(
                llm_config=self.llm_config,
                schema=RawOrganizationData.model_json_schema(),
                extraction_type="schema",
                instruction=instruction,
                extra_args={"temperature": 0.0, "max_tokens": 2000},
                chunk_token_threshold=3000,  # smaller chunks for large pages / context limit
                overlap_rate=0.1,
                apply_chunking=True,
                input_format="markdown",
            )

        return CrawlerRunConfig(
            extraction_strategy=strategy,
            word_count_threshold=0,  # don't drop short blocks (menus, contacts)
            page_timeout=30000,
            wait_until="domcontentloaded",  # "networkidle" often times out on heavy sites
            delay_before_return_html=2.0,
            magic=True,
            simulate_user=True,
        )
