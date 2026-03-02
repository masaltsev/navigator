"""Lightweight site verification: crawl a single page and ask LLM if it
belongs to the expected organization.

Level 2 of the enrichment pipeline — uses ~2K tokens per check instead of
~30K tokens for the full OrganizationProcessor pipeline.

Usage:
    verifier = SiteVerifier(deepseek_client)
    result = await verifier.verify(
        candidate_url="https://kcson-vologda.gov35.ru",
        expected_org_title="ГБУ СО «КЦСОН» г. Вологда",
        expected_inn="3525012345",
    )
    if result.is_match and result.confidence >= 0.7:
        # proceed to full harvest
"""

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import structlog
from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig
from pydantic import BaseModel, Field, model_validator

from urllib.parse import urlparse

from config.settings import get_settings
from processors.deepseek_client import DeepSeekClient

logger = structlog.get_logger(__name__)

_HARVESTER_ROOT = Path(__file__).resolve().parent.parent
_playwright_install_attempted: bool = False


def _ensure_playwright_chromium() -> bool:
    """Run 'playwright install chromium' once per process so crawl works without manual setup."""
    global _playwright_install_attempted
    if _playwright_install_attempted:
        return False
    _playwright_install_attempted = True
    try:
        logger.info("playwright_install", message="Installing Playwright Chromium (one-time)")
        settings = get_settings()
        install_env = {
            **dict(os.environ),
            "TMPDIR": settings.get_crawl4ai_browser_data_dir(),
            "PLAYWRIGHT_BROWSERS_PATH": settings.get_playwright_browsers_path(),
        }
        result = subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            cwd=str(_HARVESTER_ROOT),
            env=install_env,
            timeout=300,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            logger.warning(
                "playwright_install_failed",
                returncode=result.returncode,
                stderr=(result.stderr or "")[:500],
                stdout=(result.stdout or "")[:300],
            )
            return False
        logger.info("playwright_install", message="Playwright Chromium installed")
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        logger.warning("playwright_install_failed", error=str(e))
        return False

# Коды регионов РФ в доменах (44 = Кострома, 35 = Вологда, 36 = Воронеж и т.д.)
_REGION_CODE_HINT = (
    "Подсказка: число в домене (напр. 44, 35) часто означает код региона РФ "
    "(44 = Костромская обл., 35 = Вологодская). Сокращения типа ogc, kcson, pndi "
    "могут соответствовать названию организации (ОГЦ, КЦСОН, ПНИ и т.д.)."
)


def _domain_hint(candidate_url: str, expected_org_title: str) -> str:
    """Short hint for LLM about domain vs org name (reduces false negatives)."""
    try:
        host = (urlparse(candidate_url).netloc or "").lower().replace("www.", "")
        if not host or "." not in host:
            return ""
        name_part = host.split(".")[0]
        if any(c.isdigit() for c in name_part):
            return _REGION_CODE_HINT
    except Exception:
        pass
    return ""

_MAX_PAGE_CHARS = 6000
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
)


class VerificationOutput(BaseModel):
    """LLM-structured response for site verification."""

    is_official_site: bool = Field(
        description="True if the page is an official website (or official social media page) of the organization"
    )
    is_main_page: bool = Field(
        description="True if the URL points to the main/home page of the site (not a subpage, news article, etc.)"
    )
    org_name_found: str = Field(
        default="",
        description="Organization name as found on the page (empty if not found)",
    )
    confidence: float = Field(
        ge=0.0, le=1.0,
        description="Confidence score 0.0-1.0",
    )
    reasoning: str = Field(
        default="",
        description="Brief explanation of the decision (1-2 sentences)",
    )
    suggested_main_url: Optional[str] = Field(
        default="",
        description="If is_main_page is false, suggest the likely main page URL if visible from the page content",
    )

    @model_validator(mode="before")
    @classmethod
    def _coerce_nulls(cls, data: dict) -> dict:
        for field_name in ("org_name_found", "reasoning", "suggested_main_url"):
            if field_name in data and data[field_name] is None:
                data[field_name] = ""
        return data


@dataclass
class VerifyResult:
    """Result of a single URL verification."""

    url: str
    crawled: bool
    crawl_error: Optional[str] = None
    page_text_len: int = 0
    verification: Optional[VerificationOutput] = None

    @property
    def is_match(self) -> bool:
        return bool(
            self.verification
            and self.verification.is_official_site
            and self.verification.confidence >= 0.6
        )

    @property
    def confidence(self) -> float:
        return self.verification.confidence if self.verification else 0.0

    @property
    def is_main_page(self) -> bool:
        return bool(self.verification and self.verification.is_main_page)


_VERIFY_SYSTEM_PROMPT = """Ты — ассистент, определяющий, является ли веб-страница официальным сайтом конкретной организации.

КОНТЕКСТ: Ты проверяешь организации из сферы социального обслуживания в России — дома-интернаты, психоневрологические интернаты (ПНИ), центры социального обслуживания (КЦСОН, КЦСО), геронтологические центры, реабилитационные центры и т.п. Организации бывают государственные (ГБУ, ГБУСО, ГАУСО, ОГБУСО) и некоммерческие (АНО, ООО, БФ).

Правила:
1. Сравни название организации на странице с ожидаемым. Учитывай:
   - Сокращения: ГБУ, ГБУСО, КЦСОН, ПНИ, ДИ, КЦСО и т.д.
   - Разницу в регистре, кавычках, порядке слов
   - Полное и краткое название могут отличаться (ПНИ = психоневрологический интернат)
2. Если на странице есть ИНН — сравни с ожидаемым (при наличии). Совпадение ИНН = 100% уверенность.
3. ВАЖНО: если домен URL содержит характерные части названия организации (напр. "hadabulak-pndi" в домене для "Хадабулакский ПНДИ"), это сильный сигнал принадлежности даже при минимальном контенте на странице.
4. Агрегаторы (checko.ru, rusprofile.ru, allpans.ru и т.п.) — НЕ официальные сайты, is_official_site = false.
5. Страницы нашего каталога (navigator.vnuki.fund) — НЕ официальные сайты.
6. Коммерческие компании (магазины, рестораны, IT-компании) — НЕ подходят, если ожидается социальная организация. Одинаковое название ≠ одна организация.
6a. Если в запросе указан регион/город организации — используй его для различения одноимённых организаций (например, «Вызов» в Мурманске vs премия «Вызов»).
7. Если URL ведёт не на главную страницу (например, /news/123, /documents/...), укажи is_main_page = false и suggested_main_url.
8. Соцсети (vk.com, ok.ru, t.me) — если это ОФИЦИАЛЬНАЯ группа/канал организации, то is_official_site = true.
9. Если на странице мало текста, но домен явно соответствует организации — ставь confidence 0.6-0.7 (а не 0.0).
10. ПЕРЕЕЗД САЙТА: если на странице написано «сайт переехал», «новый адрес сайта», «перешли на ...» или подобное — установи is_official_site = true, но ОБЯЗАТЕЛЬНО укажи новый URL в suggested_main_url и упомяни переезд в reasoning. Confidence при этом 0.5-0.6 (сайт-заглушка, а не рабочий).

Верни JSON строго по схеме:
{
  "is_official_site": bool,
  "is_main_page": bool,
  "org_name_found": "название организации как на странице, или 'не найдено'",
  "confidence": 0.0-1.0,
  "reasoning": "1-2 предложения: что совпало / не совпало",
  "suggested_main_url": "если is_main_page=false, предполагаемый URL главной"
}"""


def _build_verify_user_message(
    page_text: str,
    candidate_url: str,
    expected_org_title: str,
    expected_inn: str = "",
    region_or_city: str = "",
) -> str:
    parts = [
        f"URL страницы: {candidate_url}",
        f"Ожидаемая организация: {expected_org_title}",
    ]
    if expected_inn:
        parts.append(f"Ожидаемый ИНН: {expected_inn}")
    if region_or_city:
        parts.append(f"Регион/город организации: {region_or_city}")
    parts.append(_domain_hint(candidate_url, expected_org_title))

    parts.append("--- НАЧАЛО ТЕКСТА СТРАНИЦЫ ---")
    if len(page_text) <= _MAX_PAGE_CHARS:
        parts.append(page_text)
    else:
        head_chars = _MAX_PAGE_CHARS * 2 // 3
        tail_chars = _MAX_PAGE_CHARS - head_chars
        parts.append(page_text[:head_chars])
        parts.append("\n[...контент пропущен...]\n")
        parts.append(page_text[-tail_chars:])
    parts.append("--- КОНЕЦ ТЕКСТА СТРАНИЦЫ ---")
    parts.append("Верни JSON.")

    return "\n".join(parts)


class SiteVerifier:
    """Crawls a candidate URL (single page) and verifies it with LLM."""

    def __init__(
        self,
        deepseek_client: DeepSeekClient,
        headless: bool = True,
    ):
        self._llm = deepseek_client
        self._headless = headless

    async def verify(
        self,
        candidate_url: str,
        expected_org_title: str,
        expected_inn: str = "",
        region_or_city: str = "",
    ) -> VerifyResult:
        page_text, crawl_error = await self._crawl_single_page(candidate_url)

        if crawl_error or not page_text:
            return VerifyResult(
                url=candidate_url,
                crawled=False,
                crawl_error=crawl_error or "empty page",
            )

        user_msg = _build_verify_user_message(
            page_text, candidate_url, expected_org_title, expected_inn,
            region_or_city=region_or_city,
        )

        try:
            verification = self._llm.classify(
                system_prompt=_VERIFY_SYSTEM_PROMPT,
                user_message=user_msg,
                output_model=VerificationOutput,
            )
        except Exception as exc:
            logger.warning(
                "verify_llm_error",
                url=candidate_url,
                error=str(exc),
            )
            return VerifyResult(
                url=candidate_url,
                crawled=True,
                page_text_len=len(page_text),
                crawl_error=f"LLM error: {exc}",
            )

        logger.info(
            "site_verified",
            url=candidate_url,
            is_match=verification.is_official_site,
            confidence=verification.confidence,
            org_found=verification.org_name_found[:60],
            is_main=verification.is_main_page,
        )
        if not verification.is_official_site and verification.confidence <= 0.0:
            # Debug: what did we send to LLM (helps diagnose 100% reject after restart)
            page_preview = (page_text[:400] + "…") if len(page_text) > 400 else page_text
            logger.warning(
                "site_verify_rejected",
                url=candidate_url[:80],
                expected_org=expected_org_title[:50],
                page_text_len=len(page_text),
                page_text_preview=page_preview.replace("\n", " ")[:500],
                reasoning=verification.reasoning[:200] if verification.reasoning else "",
            )

        return VerifyResult(
            url=candidate_url,
            crawled=True,
            page_text_len=len(page_text),
            verification=verification,
        )

    async def verify_batch(
        self,
        candidates: list[str],
        expected_org_title: str,
        expected_inn: str = "",
        *,
        max_candidates: int = 3,
        region_or_city: str = "",
    ) -> list[VerifyResult]:
        """Verify multiple candidates, return all results.

        Stops early if a high-confidence match on main page is found.
        """
        results: list[VerifyResult] = []

        for url in candidates[:max_candidates]:
            result = await self.verify(
                url, expected_org_title, expected_inn,
                region_or_city=region_or_city,
            )
            results.append(result)

            if result.is_match and result.is_main_page and result.confidence >= 0.8:
                logger.info("verify_early_stop", url=url, confidence=result.confidence)
                break

        return results

    async def _crawl_single_page(self, url: str) -> tuple[str, Optional[str]]:
        """Crawl a single page, return (text, error)."""
        # Force project paths so Chromium/Playwright don't use sandbox or system cache
        settings = get_settings()
        browser_dir = settings.get_crawl4ai_browser_data_dir()
        os.environ["TMPDIR"] = os.environ["TMP"] = os.environ["TEMP"] = browser_dir
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = settings.get_playwright_browsers_path()
        browser_config = BrowserConfig(
            headless=self._headless,
            enable_stealth=True,
            user_agent=get_settings().crawl4ai_user_agent or _USER_AGENT,
            user_data_dir=get_settings().get_crawl4ai_browser_data_dir(),
        )
        config = CrawlerRunConfig(
            word_count_threshold=0,
            page_timeout=20000,
            wait_until="domcontentloaded",
            delay_before_return_html=1.5,
            magic=True,
            simulate_user=True,
            cache_mode=CacheMode.BYPASS,
        )

        try:
            async with AsyncWebCrawler(config=browser_config) as crawler:
                res = await crawler.arun(url=url, config=config)
                if not res.success:
                    return "", f"crawl failed: {res.error_message}"

                text = (res.markdown or "") or (getattr(res, "fit_markdown", None) or "")
                if not text and hasattr(res, "markdown_v2") and res.markdown_v2:
                    text = res.markdown_v2.fit_markdown or ""
                if not text or len(text.strip()) < 50:
                    return "", "page too short or empty"
                return text, None
        except Exception as exc:
            err_msg = str(exc)
            # Auto-install Playwright Chromium once if missing (so harvester runs without manual setup)
            if ("Executable doesn't exist" in err_msg or "playwright install" in err_msg.lower()) and _ensure_playwright_chromium():
                try:
                    async with AsyncWebCrawler(config=browser_config) as crawler:
                        res = await crawler.arun(url=url, config=config)
                        if not res.success:
                            return "", f"crawl failed: {res.error_message}"
                        text = (res.markdown or "") or (getattr(res, "fit_markdown", None) or "")
                        if not text and hasattr(res, "markdown_v2") and res.markdown_v2:
                            text = res.markdown_v2.fit_markdown or ""
                        if not text or len(text.strip()) < 50:
                            return "", "page too short or empty"
                        return text, None
                except Exception as retry_exc:
                    return "", f"crawl exception: {retry_exc}"
            return "", f"crawl exception: {exc}"
