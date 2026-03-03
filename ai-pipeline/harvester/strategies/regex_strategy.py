"""Regex extraction for contacts (0 tokens, 0 API calls)."""

import re
from dataclasses import dataclass

PHONE_RE = re.compile(
    r"(?:\+7|8)[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}"
)
EMAIL_RE = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"
)
INN_RE = re.compile(r"\bИНН[\s:]*(\d{10,12})\b", re.IGNORECASE)
OGRN_RE = re.compile(r"\bОГРН[\s:]*(\d{13,15})\b", re.IGNORECASE)


@dataclass
class ContactExtraction:
    phones: list[str]
    emails: list[str]
    inn: str | None
    ogrn: str | None


def extract_contacts(html: str) -> ContactExtraction:
    """Extract contact data from raw HTML. 0 tokens, 0 API calls."""
    return ContactExtraction(
        phones=list(set(PHONE_RE.findall(html))),
        emails=list(set(EMAIL_RE.findall(html))),
        inn=next(iter(INN_RE.findall(html)), None),
        ogrn=next(iter(OGRN_RE.findall(html)), None),
    )
