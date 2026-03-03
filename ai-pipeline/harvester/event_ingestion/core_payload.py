"""
Формирование payload для POST /api/internal/import/event.

Содержит только поля, принимаемые бэкендом. Единая точка формирования
запроса на создание/обновление мероприятия в Core.
"""

from typing import Any, List, Optional

from prompts.schemas import EventOutput


# Поля, которые Core API принимает для import/event (источник: ImportController)
CORE_EVENT_PAYLOAD_KEYS = frozenset({
    "source_reference",
    "organizer_id",
    "title",
    "description",
    "attendance_mode",
    "online_url",
    "event_page_url",
    "rrule_string",
    "start_datetime",
    "end_datetime",
    "ai_metadata",
    "classification",
    "venues",
})


def build_core_event_payload(
    event_output: EventOutput,
    organizer_id: str,
    *,
    event_page_url: Optional[str] = None,
    start_datetime: Optional[str] = None,
    end_datetime: Optional[str] = None,
    title_override: Optional[str] = None,
    description_override: Optional[str] = None,
    ai_source_trace: Optional[List[dict]] = None,
) -> dict[str, Any]:
    """
    Собрать payload для Core API из результата LLM и переданных переопределений.

    - organizer_id обязателен (Core требует).
    - event_page_url: обычно source_url из RawEventInput (для клиентов).
    - start_datetime/end_datetime: из парсера дат или из event_output.schedule.
    - title_override/description_override: если источник доверяет своим данным больше, чем LLM.
    - ai_source_trace: массив записей { source_kind, source_url, fields_extracted } для трассировки.
    """
    payload = {
        "source_reference": event_output.source_reference,
        "organizer_id": organizer_id,
        "title": title_override if title_override is not None else event_output.title,
        "description": description_override if description_override is not None else event_output.description,
        "attendance_mode": event_output.attendance_mode,
        "online_url": event_output.online_url,
        "rrule_string": event_output.schedule.rrule_suggestion if event_output.schedule else None,
        "ai_metadata": {
            "decision": event_output.ai_metadata.decision,
            "ai_confidence_score": event_output.ai_metadata.ai_confidence_score,
            "works_with_elderly": event_output.ai_metadata.works_with_elderly,
            "ai_explanation": event_output.ai_metadata.ai_explanation,
            "ai_source_trace": ai_source_trace if ai_source_trace is not None else [],
        },
        "classification": {
            "event_category_codes": event_output.classification.event_category_codes,
            "thematic_category_codes": getattr(
                event_output.classification, "thematic_category_codes", []
            ) or [],
            "target_audience": event_output.target_audience or [],
        },
        "venues": [
            {"address_raw": v.address_raw, "address_comment": v.address_comment}
            for v in event_output.venues
        ],
    }

    if event_page_url is not None:
        payload["event_page_url"] = event_page_url
    if start_datetime is not None:
        payload["start_datetime"] = start_datetime
    if end_datetime is not None:
        payload["end_datetime"] = end_datetime

    return payload
