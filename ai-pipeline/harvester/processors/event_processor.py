"""
Оркестратор обработки мероприятий через AI-пайплайн.

Связывает: HarvestInput → Event System Prompt → DeepSeek API → EventOutput.
Аналогичен OrganizationProcessor, но использует event-специфичные промпт и схему.
"""

from typing import Callable, Optional

import structlog

from processors.deepseek_client import DeepSeekClient
from prompts.dictionaries import load_all_dictionaries
from prompts.event_prompt import build_event_system_prompt, build_event_user_message
from prompts.schemas import EntityType, EventOutput, EventSchedule, HarvestInput

logger = structlog.get_logger(__name__)


class EventProcessor:
    """Обрабатывает сырые данные о мероприятиях через LLM."""

    def __init__(self, deepseek_client: DeepSeekClient):
        self.client = deepseek_client
        self._system_prompt = build_event_system_prompt()
        logger.info(
            "Event system prompt built: ~%d chars", len(self._system_prompt)
        )

    def process(self, harvest_input: HarvestInput) -> EventOutput:
        """
        Классификация одного мероприятия через LLM.
        """
        assert harvest_input.entity_type == EntityType.EVENT

        user_message = build_event_user_message(harvest_input)

        result = self.client.classify(
            system_prompt=self._system_prompt,
            user_message=user_message,
            output_model=EventOutput,
        )

        result.source_reference = harvest_input.source_item_id
        self._validate_codes(result)

        return result

    def _validate_codes(self, result: EventOutput) -> None:
        """Post-hoc проверка кодов из справочников."""
        dicts = load_all_dictionaries()

        valid_codes = {}
        for name, items in dicts.items():
            valid_codes[name] = {str(item.get("code") or item.get("slug", "")) for item in items}

        cls = result.classification

        for code in cls.thematic_category_codes:
            if code not in valid_codes.get("thematic_categories", set()):
                logger.warning("Invalid thematic_category code: %s in event %s", code, result.title)

        for code in cls.service_codes:
            if code not in valid_codes.get("services", set()):
                logger.warning("Invalid service code: %s in event %s", code, result.title)

        for code in cls.event_category_codes:
            if code not in valid_codes.get("event_categories", set()):
                logger.warning("Invalid event_category code: %s in event %s", code, result.title)

    def process_and_sync(self, harvest_input: HarvestInput) -> dict:
        """
        Полный цикл: LLM → Pydantic → решение CREATE / UPDATE / SKIP.
        """
        event = self.process(harvest_input)

        event.existing_entity_id = harvest_input.existing_entity_id
        event.is_update = harvest_input.existing_entity_id is not None

        decision = event.ai_metadata.decision

        if decision == "rejected":
            if event.is_update:
                return {
                    "action": "mark_outdated",
                    "existing_entity_id": event.existing_entity_id,
                    "ai_explanation": event.ai_metadata.ai_explanation,
                }
            return {"action": "skipped", "reason": "rejected_new"}

        payload = to_event_payload(event)

        if decision == "accepted":
            if event.is_update:
                payload["action"] = "update"
                payload["existing_entity_id"] = event.existing_entity_id
                return {"action": "updated", "payload": payload}
            payload["action"] = "create"
            return {"action": "created", "payload": payload}

        # needs_review
        if event.is_update:
            payload["action"] = "update"
            payload["existing_entity_id"] = event.existing_entity_id
            payload["requires_review"] = True
            return {"action": "updated_needs_review", "payload": payload}
        payload["action"] = "create_draft"
        return {"action": "created_draft", "payload": payload}

    def process_batch(
        self,
        items: list[HarvestInput],
        on_success: Optional[Callable] = None,
        on_error: Optional[Callable] = None,
    ) -> list[dict]:
        """Последовательная обработка пакета мероприятий."""
        results: list[dict] = []
        for i, item in enumerate(items):
            try:
                result = self.process_and_sync(item)
                results.append(result)
                if on_success:
                    on_success(i, result)
            except Exception as e:
                logger.error("Failed to process event %s: %s", item.source_item_id, e)
                if on_error:
                    on_error(i, item, e)

        metrics = self.client.get_metrics()
        logger.info(
            "Event batch complete: %d/%d successful. Cache hit rate: %.1f%%. Est. cost: $%.4f",
            len(results),
            len(items),
            metrics["cache_hit_rate"] * 100,
            metrics["estimated_cost_usd"],
        )

        return results


def _schedule_to_start_end_iso(schedule: EventSchedule) -> tuple[str | None, str | None]:
    """Build start_datetime and end_datetime ISO strings from EventOutput.schedule (single occurrence)."""
    if not schedule.start_date or not schedule.start_time:
        return None, None
    try:
        st = (schedule.start_time or "").replace(".", ":")
        if len(st) == 5 and ":" in st:  # HH:MM
            st += ":00"
        start_dt = f"{schedule.start_date}T{st}+03:00"
        if schedule.end_date and schedule.end_time:
            et = (schedule.end_time or "").replace(".", ":")
            if len(et) == 5 and ":" in et:
                et += ":00"
            end_dt = f"{schedule.end_date}T{et}+03:00"
        else:
            from datetime import datetime, timedelta
            base = datetime.strptime(schedule.start_date + " " + (schedule.start_time or "00:00").replace(".", ":"), "%Y-%m-%d %H:%M")
            end_base = base + timedelta(hours=1)
            end_dt = end_base.strftime("%Y-%m-%dT%H:%M:%S") + "+03:00"
        return start_dt, end_dt
    except (ValueError, TypeError):
        return None, None


def to_event_payload(
    event: EventOutput,
    *,
    event_page_url: Optional[str] = None,
    start_datetime: Optional[str] = None,
    end_datetime: Optional[str] = None,
) -> dict:
    """
    Конвертация EventOutput → формат для Navigator Core API.
    event_page_url: URL страницы мероприятия (для клиентов). Если не передан, можно взять из ai_source_trace[0].source_url.
    start_datetime/end_datetime: если не переданы, выводятся из event.schedule при наличии start_date+start_time.
    """
    s, e = start_datetime, end_datetime
    if s is None and e is None:
        s, e = _schedule_to_start_end_iso(event.schedule)

    payload = {
        "source_reference": event.source_reference,
        "entity_type": "Event",
        "title": event.title,
        "description": event.description,
        "attendance_mode": event.attendance_mode,
        "online_url": event.online_url,
        "is_free": event.is_free,
        "price_description": event.price_description,
        "registration_required": event.registration_required,
        "registration_url": event.registration_url,
        "organizer_title": event.organizer_title,
        "organizer_inn": event.organizer_inn,
        "schedule": event.schedule.model_dump(),
        "ai_metadata": {
            "decision": event.ai_metadata.decision,
            "ai_explanation": event.ai_metadata.ai_explanation,
            "ai_confidence_score": event.ai_metadata.ai_confidence_score,
            "works_with_elderly": event.ai_metadata.works_with_elderly,
        },
        "classification": {
            "event_category_codes": event.classification.event_category_codes,
            "thematic_category_codes": event.classification.thematic_category_codes,
            "service_codes": event.classification.service_codes,
        },
        "venues": [
            {"address_raw": v.address_raw, "address_comment": v.address_comment}
            for v in event.venues
        ],
        "contacts": {
            "phones": event.contacts.phones,
            "emails": event.contacts.emails,
        },
        "target_audience": event.target_audience,
        "age_restriction": event.age_restriction,
        "suggested_taxonomy": [s.model_dump() for s in event.suggested_taxonomy],
    }
    if event_page_url is not None:
        payload["event_page_url"] = event_page_url
    if s is not None:
        payload["start_datetime"] = s
    if e is not None:
        payload["end_datetime"] = e
    return payload
