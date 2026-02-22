"""
Stub: registry for polymorphic prompts. Full implementation in separate workstream.
"""

from prompts.base_system_prompt import build_base_system_prompt


def get_extraction_prompt(source_kind: str, parse_config: dict) -> str:
    """
    Phase 1: single prompt for all org_website.
    Phase 2+: polymorphic by type (kcson_prompt, medical_prompt, nko_prompt, etc.)
    """
    return build_base_system_prompt()
