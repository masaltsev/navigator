"""Pydantic Settings for Harvester — single source of truth for all env vars.

Every env variable used anywhere in the Harvester codebase MUST be declared
here. Use ``get_settings()`` to obtain a cached singleton instead of calling
``os.getenv()`` directly.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


@lru_cache(maxsize=1)
def get_settings() -> "HarvesterSettings":
    return HarvesterSettings()


class HarvesterSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---- LLM (DeepSeek) ----
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek/deepseek-chat"

    # ---- Core API ----
    core_api_url: str = ""
    core_api_token: str = ""

    # ---- Dadata ----
    dadata_api_key: str = ""
    dadata_secret_key: str = ""
    dadata_use_clean: bool = False

    # ---- Web Search ----
    search_provider: str = ""  # "yandex" to force Yandex; empty = auto (DuckDuckGo)
    yandex_search_folder_id: str = ""
    yandex_search_api_key: str = ""

    # ---- Redis / Celery ----
    redis_url: str = "redis://localhost:6379/0"

    # ---- Crawl4AI ----
    crawl4ai_headless: bool = True
    crawl4ai_user_agent: str = "NavigatorHarvester/1.0 (+https://navigator.vnuki.fund)"

    # ---- Harvester API ----
    harvester_api_token: str = ""

    # ---- Logging ----
    harvester_log_format: str = "console"  # "json" for production
    harvester_log_level: str = "INFO"

    # ---- Optional / experimental ----
    firecrawl_api_key: str = ""

    # ---- Database (direct access, used by legacy scripts) ----
    db_host: str = "127.0.0.1"
    db_port: int = 5432
    db_database: str = "navigator_core"
    db_username: str = "navigator_core_user"
    db_password: str = "navigator_core_password"

    # ---- Derived helpers ----

    @property
    def redis_url_for_celery(self) -> str:
        return self.redis_url

    @property
    def deepseek_model_name(self) -> str:
        """Model name without provider prefix (e.g. 'deepseek-chat')."""
        m = self.deepseek_model
        return m.split("/", 1)[1] if "/" in m else m
