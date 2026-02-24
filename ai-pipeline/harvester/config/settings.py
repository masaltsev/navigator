"""Pydantic Settings for Harvester. All values from env."""

from pydantic_settings import BaseSettings, SettingsConfigDict


def get_settings() -> "HarvesterSettings":
    return HarvesterSettings()


class HarvesterSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek/deepseek-chat"

    # Core API (Sprint 2+)
    core_api_url: str = ""
    core_api_token: str = ""

    # Dadata (Sprint 2+)
    dadata_api_key: str = ""
    dadata_secret_key: str = ""
    dadata_use_clean: bool = False

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Crawl4AI
    crawl4ai_headless: bool = True
    crawl4ai_user_agent: str = "NavigatorHarvester/1.0 (+https://navigator.vnuki.fund)"

    # Optional
    firecrawl_api_key: str = ""

    @property
    def redis_url_for_celery(self) -> str:
        return self.redis_url
