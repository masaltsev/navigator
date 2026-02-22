"""
LLM config factory for Crawl4AI.
DeepSeek via LiteLLM. System prompt caching reduces input cost on repeated calls.
"""

import os

from crawl4ai import LLMConfig


def get_llm_config() -> LLMConfig:
    return LLMConfig(
        provider=os.getenv("DEEPSEEK_MODEL", "deepseek/deepseek-chat"),
        api_token=os.getenv("DEEPSEEK_API_KEY"),
    )
