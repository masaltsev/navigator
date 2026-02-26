"""Filters for FPG projects: direction, status, elderly relevance, dedup.

Pipeline: all projects -> direction filter -> status filter -> elderly filter -> dedup by org.
"""

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

import structlog

from aggregators.fpg.models import FPGOrganization, FPGProject

logger = structlog.get_logger(__name__)

RELEVANT_DIRECTIONS: set[str] = {
    "охрана здоровья граждан, пропаганда здорового образа жизни",
    "социальное обслуживание, социальная поддержка и защита граждан",
    "поддержка семьи, материнства, отцовства и детства",
    "поддержка проектов в области культуры и искусства",
    "поддержка проектов в области науки, образования, просвещения",
}

EXCLUDE_EVALUATIONS: set[str] = {
    "проект реализован неудовлетворительно",
    "проект, к реализации которого победитель конкурса не приступал (грант не использовался)",
}

ELDERLY_KEYWORDS: list[str] = [
    r"пожил",
    r"старш",
    r"долголет",
    r"серебрян",
    r"55\+",
    r"60\+",
    r"пенсион",
    r"геронто",
    r"деменц",
    r"альцгейм",
    r"уход\s+за",
    r"старост",
    r"престарел",
    r"ветеран",
    r"бабуш",
    r"дедуш",
    r"людям?\s+старш",
    r"граждан\w*\s+старш",
    r"возраст\w*\s+старш",
    r"третий\s+возраст",
    r"третьего\s+возраста",
    r"старш\w+\s+поколен",
    r"активн\w+\s+долголет",
    r"здоров\w+\s+долголет",
]

ELDERLY_PATTERN: re.Pattern = re.compile(
    "|".join(ELDERLY_KEYWORDS), re.IGNORECASE
)


@dataclass
class FilterStats:
    """Statistics from the filtering pipeline."""

    total_input: int = 0
    after_direction: int = 0
    after_status: int = 0
    after_elderly: int = 0
    unique_organizations: int = 0
    orgs_with_winning_projects: int = 0
    directions_breakdown: dict[str, int] = field(default_factory=dict)

    def summary(self) -> str:
        lines = [
            f"Total projects in XLSX:       {self.total_input:>7}",
            f"After direction filter:       {self.after_direction:>7}",
            f"After status filter:          {self.after_status:>7}",
            f"After elderly keyword filter: {self.after_elderly:>7}",
            f"Unique organizations:         {self.unique_organizations:>7}",
            f"  with winning projects:      {self.orgs_with_winning_projects:>7}",
        ]
        if self.directions_breakdown:
            lines.append("Direction breakdown:")
            for d, c in sorted(
                self.directions_breakdown.items(), key=lambda x: -x[1]
            ):
                lines.append(f"  {c:>5}  {d}")
        return "\n".join(lines)


def filter_by_direction(
    projects: list[FPGProject],
    directions: Optional[set[str]] = None,
) -> list[FPGProject]:
    """Keep only projects from relevant grant directions."""
    allowed = directions or RELEVANT_DIRECTIONS
    return [p for p in projects if p.grant_direction in allowed]


def filter_by_status(projects: list[FPGProject]) -> list[FPGProject]:
    """Exclude withdrawn projects and those with bad evaluations."""
    result = []
    for p in projects:
        if "отозван" in p.status.lower():
            continue
        if p.evaluation and p.evaluation in EXCLUDE_EVALUATIONS:
            continue
        result.append(p)
    return result


def filter_elderly_relevant(
    projects: list[FPGProject],
    check_title_only: bool = True,
) -> list[FPGProject]:
    """Filter projects relevant to elderly care by keyword matching.

    Matches against project title (and optionally organization name).
    Returns projects where at least one keyword is found.
    """
    result = []
    for p in projects:
        text = p.project_title
        if not check_title_only:
            text = f"{text} {p.organization_name}"
        if ELDERLY_PATTERN.search(text):
            result.append(p)
    return result


def deduplicate_by_org(
    projects: list[FPGProject],
) -> list[FPGOrganization]:
    """Group projects by organization (INN or name) into FPGOrganization."""
    org_map: dict[str, list[FPGProject]] = defaultdict(list)

    for p in projects:
        key = p.inn if p.inn else p.organization_name
        org_map[key].append(p)

    organizations: list[FPGOrganization] = []
    for key, org_projects in org_map.items():
        first = org_projects[0]
        org = FPGOrganization(
            inn=first.inn,
            ogrn=first.ogrn,
            name=first.organization_name,
            region=first.region,
            projects=org_projects,
        )
        organizations.append(org)

    organizations.sort(key=lambda o: o.project_count, reverse=True)
    return organizations


def run_filter_pipeline(
    projects: list[FPGProject],
    directions: Optional[set[str]] = None,
    include_org_name_in_keyword_search: bool = False,
) -> tuple[list[FPGOrganization], FilterStats]:
    """Full filter pipeline: direction -> status -> elderly -> dedup.

    Returns:
        Tuple of (list of FPGOrganization, FilterStats).
    """
    stats = FilterStats(total_input=len(projects))

    filtered = filter_by_direction(projects, directions)
    stats.after_direction = len(filtered)
    logger.info("Direction filter", kept=len(filtered))

    filtered = filter_by_status(filtered)
    stats.after_status = len(filtered)
    logger.info("Status filter", kept=len(filtered))

    filtered = filter_elderly_relevant(
        filtered,
        check_title_only=not include_org_name_in_keyword_search,
    )
    stats.after_elderly = len(filtered)
    logger.info("Elderly keyword filter", kept=len(filtered))

    for p in filtered:
        stats.directions_breakdown[p.grant_direction] = (
            stats.directions_breakdown.get(p.grant_direction, 0) + 1
        )

    organizations = deduplicate_by_org(filtered)
    stats.unique_organizations = len(organizations)
    stats.orgs_with_winning_projects = sum(
        1 for o in organizations if o.has_winning_project
    )

    logger.info(
        "Filter pipeline complete",
        orgs=len(organizations),
        winners=stats.orgs_with_winning_projects,
    )

    return organizations, stats
