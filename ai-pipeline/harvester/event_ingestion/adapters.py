"""
Адаптеры: преобразование источников в RawEventInput.

Каждый источник (стратегия обхода сайта, агрегатор, соцсеть) приводит
свои структуры к каноническому формату для универсального пайплайна.
"""

from typing import TYPE_CHECKING

from event_ingestion.models import (
    RawEventInput,
    SOURCE_KIND_AGGREGATOR_SILVERAGE,
    SOURCE_KIND_ORG_WEBSITE,
)

if TYPE_CHECKING:
    from aggregators.silverage.models import SilverAgeEvent
    from strategies.event_discovery import EventCandidate


def event_candidate_to_raw(candidate: "EventCandidate", source_id: str) -> RawEventInput:
    """
    EventCandidate (обход /news, /afisha на сайте организации) → RawEventInput.

    source_id: идентификатор источника в Core (source_id) или base_url сайта для трассировки.
    """
    import hashlib
    ref = hashlib.sha256(f"{candidate.url}#{candidate.title[:80]}".encode()).hexdigest()[:32]
    raw_text = f"# {candidate.title}\n\n{candidate.markdown}"
    return RawEventInput(
        source_reference=ref,
        title=candidate.title,
        raw_text=raw_text,
        source_url=candidate.url,
        source_kind=SOURCE_KIND_ORG_WEBSITE,
        discovered_from=candidate.discovered_from or source_id,
    )


def silverage_event_to_raw(event: "SilverAgeEvent") -> RawEventInput:
    """SilverAgeEvent (агрегатор silveragemap.ru) → RawEventInput."""
    raw_text = (
        f"Название: {event.title}\n\n"
        f"Описание: {event.description or ''}\n\n"
        f"Дата и время: {event.date_text or ''}\n"
        f"Место: {event.location or ''}\n"
        f"Категория на сайте: {event.category or ''}"
    )
    return RawEventInput(
        source_reference=event.source_reference,
        title=event.title,
        raw_text=raw_text[:8000],
        source_url=event.page_url or "",
        source_kind=SOURCE_KIND_AGGREGATOR_SILVERAGE,
        date_text=event.date_text,
        location=event.location,
        is_online=event.is_online,
        registration_url=event.registration_url,
        category_from_source=event.category,
        discovered_from="silverage_platform",
    )
