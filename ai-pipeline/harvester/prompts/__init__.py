# Polymorphic prompts for Navigator Harvester v1 classification pipeline.
#
# Public API:
#   prompts.schemas          — Pydantic models (HarvestInput, OrganizationOutput, EventOutput)
#   prompts.dictionaries     — Seeder loading and prompt formatting
#   prompts.organization_prompt — System prompt builder for organizations
#   prompts.event_prompt     — System prompt builder for events
#   prompts.examples         — Few-shot examples
#
# Legacy (Crawl4AI extraction, Phase 1):
#   prompts.base_system_prompt — Minimal system prompt used by strategy_router
#   prompts.prompt_registry    — Registry stub for Phase 1
