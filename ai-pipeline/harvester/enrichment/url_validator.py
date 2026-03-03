"""
URL validation for harvest pipeline.

Sprint 3.6 batch test showed 2/5 errors were caused by invalid URLs in the DB
(truncated domains, missing TLD). This module validates URLs before crawling.
"""

import re
from urllib.parse import urlparse

_URL_RE = re.compile(
    r'^https?://[a-zA-Z0-9]([a-zA-Z0-9\-]*[a-zA-Z0-9])?'
    r'(\.[a-zA-Z0-9]([a-zA-Z0-9\-]*[a-zA-Z0-9])?)*'
    r'\.[a-zA-Z]{2,}'
    r'(/.*)?$'
)


def validate_url(url: str) -> tuple[bool, str]:
    """
    Validate a URL for crawling.

    Returns (is_valid, reason). If valid, reason is empty string.
    Catches issues found in Sprint 3.6 batch test:
      - Truncated domains (missing TLD)
      - Missing scheme
      - Empty/whitespace URLs
    """
    if not url or not url.strip():
        return False, "empty_url"

    url = url.strip()

    if not url.startswith(("http://", "https://")):
        return False, "missing_scheme"

    parsed = urlparse(url)

    if not parsed.hostname:
        return False, "no_hostname"

    hostname = parsed.hostname
    if '.' not in hostname:
        return False, "no_tld"

    tld = hostname.rsplit('.', 1)[-1]
    if len(tld) < 2:
        return False, "truncated_tld"

    if not _URL_RE.match(url):
        return False, "invalid_format"

    return True, ""


def filter_valid_urls(sources: list[dict]) -> tuple[list[dict], list[dict]]:
    """
    Split sources into valid and invalid based on URL validation.

    Returns (valid_sources, invalid_sources).
    """
    valid: list[dict] = []
    invalid: list[dict] = []

    for src in sources:
        url = src.get("url", "")
        is_valid, reason = validate_url(url)
        if is_valid:
            valid.append(src)
        else:
            invalid.append({**src, "_invalid_reason": reason})

    return valid, invalid
