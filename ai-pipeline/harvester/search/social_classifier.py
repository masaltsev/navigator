"""Classify URLs as social media pages and extract identifiers.

Recognises VK, OK, Telegram URLs and extracts group/channel IDs
for storage in the sources table and organization fields.
"""

import re
from dataclasses import dataclass
from enum import Enum
from urllib.parse import urlparse


class SocialPlatform(str, Enum):
    VK = "vk_group"
    OK = "ok_group"
    TELEGRAM = "tg_channel"
    NONE = "none"


@dataclass(frozen=True)
class SocialLink:
    """Parsed social media link."""

    platform: SocialPlatform
    url: str
    slug: str
    numeric_id: int | None

    @property
    def is_social(self) -> bool:
        return self.platform != SocialPlatform.NONE

    @property
    def source_kind(self) -> str:
        return self.platform.value


_VK_CLUB_RE = re.compile(r'vk\.com/club(\d+)')
_VK_PUBLIC_RE = re.compile(r'vk\.com/public(\d+)')
_VK_SLUG_RE = re.compile(r'vk\.com/([a-zA-Z][\w.]+)')
_OK_GROUP_RE = re.compile(r'ok\.ru/group/(\d+)')
_OK_PROFILE_RE = re.compile(r'ok\.ru/profile/(\d+)')
_OK_SLUG_RE = re.compile(r'ok\.ru/([a-zA-Z][\w.]+)')
_TG_RE = re.compile(r't\.me/([a-zA-Z][\w]+)')


def _is_social_post(url: str) -> bool:
    """Check if a social URL points to a specific post, not a group/page root."""
    path = urlparse(url).path.lower()
    post_indicators = (
        "/topic/", "/topic-",
        "/wall", "/wall-",
        "/photo", "/photo-",
        "/video", "/video-",
        "/album", "/album-",
        "/market", "/product",
        "/clip",
        "/article",
    )
    return any(indicator in path for indicator in post_indicators)


def classify_social_url(url: str) -> SocialLink:
    """Classify a URL and extract social media identifiers.

    Returns SocialLink with platform=NONE if URL is not a social page.
    Rejects post/topic/wall URLs — only group/profile root pages are accepted.

    Examples:
        "https://vk.com/club12345"                        -> VK, id=12345
        "https://vk.com/kcson_vol"                        -> VK, slug="kcson_vol"
        "https://ok.ru/group/54321"                       -> OK, id=54321
        "https://ok.ru/group/54321/topic/999"             -> NONE (post)
        "https://t.me/kcson_news"                         -> TG, slug="kcson_news"
        "https://example.com"                             -> NONE
    """
    url = url.strip().rstrip('/')
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()

    if _is_social_post(url):
        return SocialLink(SocialPlatform.NONE, url, "", None)

    if 'vk.com' in hostname or 'vk.ru' in hostname:
        m = _VK_CLUB_RE.search(url)
        if m:
            return SocialLink(SocialPlatform.VK, url, f"club{m.group(1)}", int(m.group(1)))
        m = _VK_PUBLIC_RE.search(url)
        if m:
            return SocialLink(SocialPlatform.VK, url, f"public{m.group(1)}", int(m.group(1)))
        m = _VK_SLUG_RE.search(url)
        if m:
            slug = m.group(1)
            if slug not in ("share", "away", "feed", "im", "login", "wall"):
                return SocialLink(SocialPlatform.VK, url, slug, None)

    if 'ok.ru' in hostname:
        m = _OK_GROUP_RE.search(url)
        if m:
            return SocialLink(SocialPlatform.OK, url, f"group/{m.group(1)}", int(m.group(1)))
        m = _OK_PROFILE_RE.search(url)
        if m:
            return SocialLink(SocialPlatform.OK, url, f"profile/{m.group(1)}", int(m.group(1)))
        m = _OK_SLUG_RE.search(url)
        if m:
            slug = m.group(1)
            if slug not in ("feed", "messages", "settings", "game"):
                return SocialLink(SocialPlatform.OK, url, slug, None)

    if 't.me' in hostname:
        m = _TG_RE.search(url)
        if m:
            slug = m.group(1)
            if slug not in ("share", "proxy", "addstickers", "joinchat"):
                return SocialLink(SocialPlatform.TELEGRAM, url, slug, None)

    return SocialLink(SocialPlatform.NONE, url, "", None)


def extract_social_links(urls: list[str]) -> list[SocialLink]:
    """Classify a list of URLs and return only social media links."""
    return [link for url in urls if (link := classify_social_url(url)).is_social]
