"""
Single entry point for "harvest one URL → organization result + Core payload".

Crawl (multi-page or single) → optional site extract / additional_context
→ OrganizationProcessor → optional Dadata geocode → to_core_import_payload.

Callers (tasks, enrichment_pipeline, run_single_url) use the result/payload
and are responsible for calling Core API (import_organizer, update_source).
"""

from __future__ import annotations

from typing import Any, Optional

from config.settings import get_settings


def _build_condensed_text(fields: dict, url: str) -> str:
    """Convert SiteExtractor output to compact text for LLM (~1–2K chars)."""
    parts = [f"URL: {url}"]
    if fields.get("platform"):
        parts.append(f"Платформа: {fields['platform']}")
    if fields.get("title"):
        parts.append(f"Название: {fields['title']}")
    if fields.get("short_title"):
        parts.append(f"Краткое название: {fields['short_title']}")
    if fields.get("description"):
        parts.append(f"\nОписание:\n{fields['description']}")
    if fields.get("address_raw"):
        parts.append(f"\nАдрес: {fields['address_raw']}")
    if fields.get("phones"):
        parts.append(f"Телефоны: {', '.join(fields['phones'])}")
    if fields.get("emails"):
        parts.append(f"Email: {', '.join(fields['emails'])}")
    if fields.get("director"):
        parts.append(f"Руководитель: {fields['director']}")
    if fields.get("work_schedule"):
        parts.append(f"Режим работы: {fields['work_schedule']}")
    if fields.get("vk_url"):
        parts.append(f"VK: {fields['vk_url']}")
    if fields.get("ok_url"):
        parts.append(f"OK: {fields['ok_url']}")
    return "\n".join(parts)


async def run_organization_harvest(
    url: str,
    *,
    source_id: str = "harvest",
    source_item_id: Optional[str] = None,
    existing_entity_id: Optional[str] = None,
    multi_page: bool = True,
    enrich_geo: bool = True,
    additional_context: str = "",
    source_kind: str = "org_website",
    try_site_extractor: bool = False,
    deepseek_client: Optional[Any] = None,
) -> dict:
    """Run crawl → classify → [Dadata] and return result + Core payload.

    Returns a dict with:
      - success: bool
      - result: OrganizationProcessor result (if success)
      - payload: dict for Core import_organizer (if success)
      - crawl_meta: dict (pages_attempted, pages_success)
      - error: str | None (if not success)
    """
    settings = get_settings()

    if multi_page:
        from strategies.multi_page import MultiPageCrawler

        crawler = MultiPageCrawler(max_subpages=5)
        crawl_result = await crawler.crawl_organization(url)
        if not crawl_result.success:
            return {
                "success": False,
                "error": "crawl_failed",
                "crawl_meta": {
                    "pages_attempted": crawl_result.total_pages_attempted,
                    "pages_success": crawl_result.total_pages_success,
                },
            }
        markdown = crawl_result.merged_markdown
        crawl_meta = {
            "pages_attempted": crawl_result.total_pages_attempted,
            "pages_success": crawl_result.total_pages_success,
        }
    else:
        from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig

        browser_config = BrowserConfig(
            headless=True,
            enable_stealth=True,
            user_agent=settings.crawl4ai_user_agent,
        )
        run_config = CrawlerRunConfig(
            word_count_threshold=0,
            page_timeout=30000,
            wait_until="domcontentloaded",
            delay_before_return_html=2.0,
            magic=True,
            simulate_user=True,
            cache_mode=CacheMode.BYPASS,
        )
        async with AsyncWebCrawler(config=browser_config) as c:
            res = await c.arun(url=url, config=run_config)
        if not res.success:
            return {
                "success": False,
                "error": "crawl_failed",
                "crawl_meta": {"pages_attempted": 1, "pages_success": 0},
            }
        markdown = res.markdown or res.fit_markdown or ""
        crawl_meta = {"pages_attempted": 1, "pages_success": 1}

    if not markdown.strip():
        return {
            "success": False,
            "error": "empty_markdown",
            "crawl_meta": crawl_meta,
        }

    raw_text = markdown[:30000]
    site_extraction = None
    if try_site_extractor:
        from strategies.site_extractors import SiteExtractorRegistry

        extracted = SiteExtractorRegistry.extract_if_known(url, markdown)
        if extracted and extracted.get("title"):
            raw_text = _build_condensed_text(extracted, url)
            site_extraction = extracted
    if additional_context:
        raw_text = f"{additional_context}\n\n---\n\n{raw_text}"

    from prompts.schemas import EntityType, HarvestInput
    from processors.organization_processor import OrganizationProcessor, to_core_import_payload
    from processors.deepseek_client import DeepSeekClient

    client = deepseek_client or DeepSeekClient(
        api_key=settings.deepseek_api_key,
        model=settings.deepseek_model_name,
    )
    processor = OrganizationProcessor(deepseek_client=client)

    harvest_input = HarvestInput(
        source_id=source_id,
        source_item_id=source_item_id or url,
        entity_type=EntityType.ORGANIZATION,
        raw_text=raw_text,
        source_url=url,
        source_kind=source_kind,
        existing_entity_id=existing_entity_id,
    )

    result = processor.process(harvest_input)

    geo_results = None
    if enrich_geo and result.venues:
        from enrichment.dadata_client import DadataClient

        dadata = DadataClient(
            api_key=settings.dadata_api_key,
            secret_key=settings.dadata_secret_key,
            use_clean=settings.dadata_use_clean,
        )
        if dadata.enabled:
            addresses = [v.address_raw for v in result.venues]
            geo_results = await dadata.geocode_batch(addresses)

    payload = to_core_import_payload(result, geo_results=geo_results)
    llm_metrics = client.get_metrics() if hasattr(client, "get_metrics") else {}

    return {
        "success": True,
        "result": result,
        "payload": payload,
        "crawl_meta": crawl_meta,
        "geo_results": geo_results,
        "llm_metrics": llm_metrics,
        "site_extraction": site_extraction,
        "error": None,
    }
