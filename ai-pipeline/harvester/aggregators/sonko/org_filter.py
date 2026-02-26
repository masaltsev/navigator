"""Filters for SONKO registry: OKVED, name keywords, dedup by INN.

Pipeline: all entries -> OKVED filter -> name keyword filter -> dedup by INN.

Unlike FPG (which filters by grant direction + elderly keywords in project titles),
SONKO filtering uses OKVED codes and organization names because the registry
has no project-level data -- only organization metadata.
"""

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

import structlog

from aggregators.sonko.models import SONKOEntry, SONKOOrganization

logger = structlog.get_logger(__name__)

# OKVED groups directly relevant to elderly care / social services
ELDERLY_OKVED_PREFIXES: set[str] = {
    "87",  # Деятельность по уходу с обеспечением проживания
    "88",  # Предоставление социальных услуг без обеспечения проживания
}

# Broader OKVED groups that _may_ contain elderly-relevant organizations
BROADER_OKVED_PREFIXES: set[str] = {
    "86",  # Деятельность в области здравоохранения
    "93",  # Деятельность в области спорта, отдыха и развлечений
    "96",  # Деятельность по предоставлению прочих персональных услуг
}

ELDERLY_KEYWORDS: list[str] = [
    r"пожил",
    r"старш\w+\s+(?:поколен|возраст|людей|граждан)",
    r"долголет",
    r"серебрян",
    r"пенсион",
    r"престарел",
    r"ветеран",
    r"геронто",
    r"деменц",
    r"альцгейм",
    r"дом\w*\s+(?:для\s+)?престарел",
    r"интернат",
    r"хоспис",
    r"паллиат",
    r"соц\w*\s*обслуж",
    r"реабилит",
    r"уход\w*\s+за",
    r"инвалид",
    r"маломоб",
    r"людей\s+(?:с\s+)?ограничен",
]

ELDERLY_PATTERN: re.Pattern = re.compile(
    "|".join(ELDERLY_KEYWORDS), re.IGNORECASE
)


@dataclass
class FilterStats:
    """Statistics from the SONKO filtering pipeline."""

    total_entries: int = 0
    unique_inns_total: int = 0
    after_okved: int = 0
    after_name_kw: int = 0
    combined_unique: int = 0
    by_okved_only: int = 0
    by_name_only: int = 0
    by_both: int = 0
    okved_breakdown: dict[str, int] = field(default_factory=dict)

    def summary(self) -> str:
        lines = [
            f"Total entries in XLSX:        {self.total_entries:>7}",
            f"Unique INNs total:           {self.unique_inns_total:>7}",
            f"After OKVED filter (87,88):  {self.after_okved:>7}",
            f"After name keyword filter:   {self.after_name_kw:>7}",
            f"Combined unique orgs:        {self.combined_unique:>7}",
            f"  by OKVED only:             {self.by_okved_only:>7}",
            f"  by name keyword only:      {self.by_name_only:>7}",
            f"  by both:                   {self.by_both:>7}",
        ]
        if self.okved_breakdown:
            lines.append("OKVED breakdown (matched orgs):")
            for code, count in sorted(
                self.okved_breakdown.items(), key=lambda x: -x[1]
            ):
                lines.append(f"  {count:>5}  {code}")
        return "\n".join(lines)


def filter_by_okved(
    entries: list[SONKOEntry],
    prefixes: Optional[set[str]] = None,
) -> list[SONKOEntry]:
    """Keep entries with OKVED codes in the elderly-relevant set."""
    allowed = prefixes or ELDERLY_OKVED_PREFIXES
    return [e for e in entries if e.okved_prefix in allowed]


def filter_by_name_keywords(
    entries: list[SONKOEntry],
) -> list[SONKOEntry]:
    """Keep entries where the org name matches elderly-relevant keywords."""
    return [e for e in entries if ELDERLY_PATTERN.search(e.full_name)]


def deduplicate_by_inn(
    entries: list[SONKOEntry],
) -> list[SONKOOrganization]:
    """Group entries by INN into SONKOOrganization objects."""
    inn_map: dict[str, list[SONKOEntry]] = defaultdict(list)

    for e in entries:
        if e.inn:
            inn_map[e.inn].append(e)

    organizations: list[SONKOOrganization] = []
    for inn, org_entries in inn_map.items():
        first = org_entries[0]
        org = SONKOOrganization(
            inn=inn,
            ogrn=first.ogrn,
            full_name=first.full_name,
            short_name=first.short_name,
            address=first.address,
            okved=first.okved,
            legal_form=first.legal_form,
            entries=org_entries,
        )
        organizations.append(org)

    organizations.sort(key=lambda o: o.entry_count, reverse=True)
    return organizations


def run_filter_pipeline(
    entries: list[SONKOEntry],
    okved_prefixes: Optional[set[str]] = None,
    include_broader_okved: bool = False,
) -> tuple[list[SONKOOrganization], FilterStats]:
    """Full filter pipeline: OKVED ∪ name keywords -> dedup by INN.

    Unlike FPG's sequential filtering, SONKO uses a union of two
    independent filters (OKVED OR name keyword) to maximize recall.
    """
    stats = FilterStats(total_entries=len(entries))

    all_inns = {e.inn for e in entries if e.inn}
    stats.unique_inns_total = len(all_inns)

    prefixes = okved_prefixes or ELDERLY_OKVED_PREFIXES
    if include_broader_okved:
        prefixes = prefixes | BROADER_OKVED_PREFIXES

    okved_matched = filter_by_okved(entries, prefixes)
    stats.after_okved = len(okved_matched)
    okved_inns = {e.inn for e in okved_matched}
    logger.info("SONKO OKVED filter", kept=len(okved_matched), unique_inns=len(okved_inns))

    name_matched = filter_by_name_keywords(entries)
    stats.after_name_kw = len(name_matched)
    name_inns = {e.inn for e in name_matched}
    logger.info("SONKO name filter", kept=len(name_matched), unique_inns=len(name_inns))

    combined_inns = okved_inns | name_inns
    combined_entries = [e for e in entries if e.inn in combined_inns]

    organizations = deduplicate_by_inn(combined_entries)
    stats.combined_unique = len(organizations)

    stats.by_both = len(okved_inns & name_inns)
    stats.by_okved_only = len(okved_inns - name_inns)
    stats.by_name_only = len(name_inns - okved_inns)

    for org in organizations:
        prefix = org.okved_prefix
        if prefix:
            stats.okved_breakdown[prefix] = stats.okved_breakdown.get(prefix, 0) + 1

    logger.info(
        "SONKO filter pipeline complete",
        orgs=len(organizations),
        okved_only=stats.by_okved_only,
        name_only=stats.by_name_only,
        both=stats.by_both,
    )

    return organizations, stats
