"""
LLM config factory for Crawl4AI.
DeepSeek via LiteLLM. System prompt caching reduces input cost on repeated calls.
"""

from crawl4ai import LLMConfig

from config.settings import get_settings


def get_llm_config() -> LLMConfig:
    settings = get_settings()
    return LLMConfig(
        provider=settings.deepseek_model,
        api_token=settings.deepseek_api_key,
    )
