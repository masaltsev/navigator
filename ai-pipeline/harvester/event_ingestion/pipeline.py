"""
Универсальный пайплайн приёма мероприятий.

Шаги:
  1. Парсинг дат: если в raw есть date_text и нет start/end — парсим в ISO.
  2. Классификация: RawEventInput → HarvestInput → EventProcessor (DeepSeek) → EventOutput.
  3. Сборка payload для Core: EventOutput + raw (event_page_url, даты, trace) → build_core_event_payload.

На выходе — один и тот же формат payload для POST /api/internal/import/event
независимо от источника (агрегатор, сайт организации, соцсеть).
"""

from __future__ import annotations

from typing import Optional

import structlog

# When LLM decision is "rejected", pipeline returns None — caller must not import.
REJECTED_DECISION = "rejected"

from event_ingestion.core_payload import build_core_event_payload
from event_ingestion.models import RawEventInput
from processors.deepseek_client import DeepSeekClient
from processors.event_processor import EventProcessor, _schedule_to_start_end_iso
from prompts.schemas import EntityType, EventOutput, HarvestInput
from utils.date_parse import parse_date_text_to_iso

logger = structlog.get_logger(__name__)


def run_event_ingestion_pipeline(
    raw: RawEventInput,
    organizer_id: str,
    *,
    event_processor: Optional[EventProcessor] = None,
    use_llm_classification: bool = True,
    title_override: Optional[str] = None,
    description_override: Optional[str] = None,
) -> Optional[dict]:
    """
    Прогон сырого мероприятия через единый пайплайн → payload для Core API.

    - raw: канонический вход из любого источника (после адаптера).
    - organizer_id: обязательный идентификатор организатора в Core.
    - event_processor: если не передан, создаётся новый (один раз на вызов).
    - use_llm_classification: если False, используется только парсинг дат и дефолтная классификация (для тестов или когда LLM недоступен).
    - title_override/description_override: подставляются в payload вместо полей из LLM (например, сохраняем оригинальные title/description от агрегатора).

    Возвращает dict, готовый для core_client.import_event(payload), или None,
    если LLM вернул decision="rejected" — такие события не импортировать в Core.
    """
    from config.settings import get_settings

    start_iso = raw.start_datetime_iso
    end_iso = raw.end_datetime_iso
    if (not start_iso or not end_iso) and raw.date_text:
        parsed_start, parsed_end = parse_date_text_to_iso(raw.date_text)
        if parsed_start:
            start_iso = parsed_start
        if parsed_end:
            end_iso = parsed_end

    ai_source_trace = [
        {
            "source_kind": raw.source_kind,
            "source_url": raw.source_url,
            "fields_extracted": ["title", "description", "date", "location", "classification"],
        }
    ]

    if not use_llm_classification:
        payload = _build_fallback_payload(raw, organizer_id, start_iso, end_iso, ai_source_trace)
        return payload

    processor = event_processor
    if processor is None:
        settings = get_settings()
        client = DeepSeekClient(
            api_key=settings.deepseek_api_key,
            model=settings.deepseek_model_name,
        )
        processor = EventProcessor(deepseek_client=client)

    harvest_input = HarvestInput(
        source_id=raw.discovered_from or "event_ingestion",
        source_item_id=raw.source_reference,
        entity_type=EntityType.EVENT,
        raw_text=raw.raw_text[:15000],
        source_url=raw.source_url,
        source_kind=raw.source_kind,
        region_hint=raw.region_hint,
    )
    try:
        event_output = processor.process(harvest_input)
        event_output.source_reference = raw.source_reference
    except Exception as e:
        logger.warning("event_ingestion_llm_failed", ref=raw.source_reference, error=str(e))
        payload = _build_fallback_payload(raw, organizer_id, start_iso, end_iso, ai_source_trace)
        return payload

    if event_output.ai_metadata.decision == REJECTED_DECISION:
        logger.info(
            "event_ingestion_rejected",
            ref=raw.source_reference,
            title=event_output.title[:60],
            score=event_output.ai_metadata.ai_confidence_score,
        )
        return None

    if not start_iso and not end_iso and event_output.schedule:
        start_iso, end_iso = _schedule_to_start_end_iso(event_output.schedule)

    attendance_mode = "online" if raw.is_online else event_output.attendance_mode
    online_url = raw.registration_url or event_output.online_url
    event_output.attendance_mode = attendance_mode
    event_output.online_url = online_url

    return build_core_event_payload(
        event_output,
        organizer_id,
        event_page_url=raw.source_url,
        start_datetime=start_iso,
        end_datetime=end_iso,
        title_override=title_override or raw.title,
        description_override=description_override,
        ai_source_trace=ai_source_trace,
    )


def _build_fallback_payload(
    raw: RawEventInput,
    organizer_id: str,
    start_iso: Optional[str],
    end_iso: Optional[str],
    ai_source_trace: list,
) -> dict:
    """Payload без LLM: дефолтная классификация и метаданные."""
    from prompts.schemas import (
        AIConfidenceMetadata,
        EventClassification,
        EventOutput,
        EventSchedule,
    )

    schedule = EventSchedule()
    fake_output = EventOutput(
        source_reference=raw.source_reference,
        title=raw.title,
        description=raw.raw_text[:2000] if raw.raw_text else "",
        attendance_mode="online" if raw.is_online else "offline",
        online_url=raw.registration_url,
        schedule=schedule,
        ai_metadata=AIConfidenceMetadata(
            decision="needs_review",
            ai_confidence_score=0.5,
            works_with_elderly=True,
            ai_explanation="Классификация не выполнена (LLM недоступен или ошибка). Требуется ручная проверка.",
        ),
        classification=EventClassification(
            event_category_codes=[],
            thematic_category_codes=[],
            service_codes=[],
        ),
        target_audience=["elderly"],
    )
    return build_core_event_payload(
        fake_output,
        organizer_id,
        event_page_url=raw.source_url,
        start_datetime=start_iso,
        end_datetime=end_iso,
        title_override=raw.title,
        description_override=raw.raw_text[:2000] if raw.raw_text else None,
        ai_source_trace=ai_source_trace,
    )
