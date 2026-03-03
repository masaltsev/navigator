"""
Markdown extractor for *.socinfo.ru sites.

All socinfo.ru sites (KCSON, CSO, social services) share the EISRF platform
with an identical markdown layout after Crawl4AI processing:

  Header:   [На главную - socinfo.ru]  →  logo  →  org name (1-3 lines)
  Sidebar:  phone  →  calendar  →  ## Адрес / ## Контакты  →  address
  Content:  # Главная / # Контакты  →  description / contact details
  Footer:   © <short_name> . Использование материалов…  Разработка… socinfo.ru

Validated against 8 socinfo.ru sites from Sprint 3.6 batch test
(irkcson.aln, cso-kaltan.kmr, kcson.stv, prig-kcson.aln, csondolzh.orl,
kcso-alagir.aln, csogpvi-osinniki.kmr, kcson-kr.adg, bf-bitdobru.aln).
"""

from __future__ import annotations

import re
from urllib.parse import urlparse


PLATFORM_MARKER = "[На главную - socinfo.ru]"
FOOTER_MARKER = "Разработка и дизайн сайта [socinfo.ru]"

PHONE_RE = re.compile(
    r"(?:\+7|8)[\s\-]?\(?\d{3,5}\)?[\s\-]?\d[\s\-]?\d[\s\-]?\d[\s\-]?\d[\s\-]?\d(?:[\s\-]?\d)*"
)
EMAIL_RE = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"
)
POSTAL_CODE_RE = re.compile(r"\b(\d{6})\b")

NOISE_EMAILS = {
    "mintrud_ra@mail.ru", "minsotc@mail.ru",
}


class SocinfoExtractor:
    """
    Extract structured org data from socinfo.ru markdown.

    Returns a dict with keys:
      title, short_title, address_raw, phones, emails,
      director, work_schedule, description, vk_url, ok_url
    """

    def extract(self, markdown: str, url: str = "") -> dict:
        lines = markdown.splitlines()
        return {
            "platform": "socinfo.ru",
            "title": self._extract_title(lines),
            "short_title": self._extract_short_title(lines),
            "address_raw": self._extract_address(lines),
            "phones": self._extract_phones(markdown),
            "emails": self._extract_emails(markdown),
            "director": self._extract_director(lines),
            "work_schedule": self._extract_schedule(lines),
            "description": self._extract_description(lines),
            "vk_url": self._extract_social(markdown, "vk.com"),
            "ok_url": self._extract_social(markdown, "ok.ru"),
        }

    # ------------------------------------------------------------------
    # Title: org name lines between the logo and the menu / accessibility link
    # ------------------------------------------------------------------

    def _extract_title(self, lines: list[str]) -> str:
        collecting = False
        title_parts: list[str] = []

        for line in lines:
            stripped = line.strip()

            if stripped.startswith("[![") and "](" in stripped and stripped.endswith(")"):
                collecting = True
                continue

            if collecting:
                if (
                    stripped.startswith("[")
                    or stripped.startswith("*")
                    or stripped.startswith("8 ")
                    or stripped.startswith("для слабовидящих")
                    or not stripped
                ):
                    if title_parts:
                        break
                    continue

                if "для слабовидящих" in stripped:
                    cleaned = re.sub(r"\[.*?\]\(.*?\)", "", stripped).strip()
                    if cleaned:
                        title_parts.append(cleaned)
                    break

                title_parts.append(stripped)

        title = " ".join(title_parts).strip()
        title = re.sub(r"\s+", " ", title)
        return title

    def _extract_short_title(self, lines: list[str]) -> str:
        for line in lines:
            if line.startswith("© ") and "socinfo" not in line:
                match = re.match(r"© (.+?)\s*\.", line)
                if match:
                    return match.group(1).strip().strip('"').strip("«").strip("»")
        return ""

    # ------------------------------------------------------------------
    # Address: from ## Адрес / ## Контакты / #### Контакты section
    # ------------------------------------------------------------------

    def _extract_address(self, lines: list[str]) -> str:
        in_address = False
        addr_parts: list[str] = []

        for line in lines:
            stripped = line.strip()

            if re.match(r"^#{1,4}\s*(Адрес|Контакты)\s*$", stripped):
                in_address = True
                continue

            if in_address:
                if stripped.startswith("#") or stripped.startswith("[!["):
                    break
                if not stripped or stripped.startswith("["):
                    if addr_parts:
                        break
                    continue

                clean = stripped.rstrip("\\").strip()
                clean = re.sub(r"\*+", "", clean).strip()
                if clean.startswith("Адрес:"):
                    clean = clean[6:].strip()
                if clean.startswith("**Адрес:**"):
                    clean = clean[10:].strip()

                if POSTAL_CODE_RE.match(clean) or re.search(r"(область|край|респ|район|г\.|ул\.|д\.|пер\.)", clean, re.I):
                    addr_parts.append(clean)
                elif addr_parts:
                    addr_parts.append(clean)
                    if re.search(r"д\.\s*\d|дом\s*\d", clean, re.I):
                        break

        return ", ".join(addr_parts).replace(",  ,", ",").replace(",,", ",").strip(", ")

    # ------------------------------------------------------------------
    # Phones: all matches, deduplicated
    # ------------------------------------------------------------------

    def _extract_phones(self, markdown: str) -> list[str]:
        raw = PHONE_RE.findall(markdown)
        seen: set[str] = set()
        result: list[str] = []
        for p in raw:
            normalized = re.sub(r"[\s\-\(\)]", "", p)
            if normalized not in seen and len(normalized) >= 11:
                seen.add(normalized)
                result.append(p.strip())
        return result

    # ------------------------------------------------------------------
    # Emails: filter out noise (platform/ministry emails)
    # ------------------------------------------------------------------

    def _extract_emails(self, markdown: str) -> list[str]:
        raw = EMAIL_RE.findall(markdown)
        return list({
            e.lower() for e in raw
            if e.lower() not in NOISE_EMAILS
            and not e.lower().endswith("@socinfo.ru")
        })

    # ------------------------------------------------------------------
    # Director: **Директор:** Name or pattern
    # ------------------------------------------------------------------

    def _extract_director(self, lines: list[str]) -> str:
        for i, line in enumerate(lines):
            stripped = line.strip().replace("**", "")
            if re.match(r"^Директор\s*:", stripped, re.I):
                name = re.sub(r"^Директор\s*:\s*", "", stripped, flags=re.I).strip()
                if not name and i + 1 < len(lines):
                    name = lines[i + 1].strip().replace("**", "").strip()
                return name
        return ""

    # ------------------------------------------------------------------
    # Work schedule
    # ------------------------------------------------------------------

    def _extract_schedule(self, lines: list[str]) -> str:
        in_schedule = False
        parts: list[str] = []

        for line in lines:
            stripped = line.strip().replace("**", "").replace("*", "")
            if re.match(r"(Режим работы|РЕЖИМ И ГРАФИК|График приема)", stripped, re.I):
                in_schedule = True
                label_content = re.sub(r"^.*?:\s*", "", stripped).strip()
                if label_content:
                    parts.append(label_content)
                continue
            if in_schedule:
                if not stripped or stripped.startswith("#") or stripped.startswith("["):
                    if parts:
                        break
                    continue
                if re.search(r"(понедельник|вторник|пн|с \d|выходн|перерыв|суббот)", stripped, re.I):
                    parts.append(stripped)
                elif parts:
                    break

        return "; ".join(parts)

    # ------------------------------------------------------------------
    # Description: main content after # Главная
    # ------------------------------------------------------------------

    def _extract_description(self, lines: list[str]) -> str:
        in_content = False
        desc_parts: list[str] = []
        para_count = 0

        for line in lines:
            stripped = line.strip()
            if stripped == "# Главная" or stripped == "# Контакты":
                in_content = True
                continue
            if in_content:
                if stripped.startswith("# ") or stripped.startswith("  * [ВКонтакте"):
                    break
                if stripped.startswith("[![") or stripped.startswith("!["):
                    continue
                if stripped.startswith("[") and "](" in stripped:
                    continue
                if not stripped:
                    if desc_parts:
                        para_count += 1
                    if para_count >= 4:
                        break
                    continue

                clean = re.sub(r"\*+", "", stripped).strip()
                clean = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", clean)
                if clean and len(clean) > 10:
                    desc_parts.append(clean)

        return "\n".join(desc_parts[:15])

    # ------------------------------------------------------------------
    # Social links
    # ------------------------------------------------------------------

    def _extract_social(self, markdown: str, domain: str) -> str:
        pattern = re.compile(
            rf"https?://(www\.)?{re.escape(domain)}/[a-zA-Z0-9_/\-]+"
        )
        for match in pattern.finditer(markdown):
            url = match.group()
            if "/share" not in url and "share2" not in url:
                return url
        return ""
