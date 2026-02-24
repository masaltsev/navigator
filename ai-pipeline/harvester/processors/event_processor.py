"""
Оркестратор обработки мероприятий через AI-пайплайн.

Связывает: HarvestInput → Event System Prompt → DeepSeek API → EventOutput.
Аналогичен OrganizationProcessor, но использует event-специфичные промпт и схему.
"""

import logging
from typing import Callable, Optional

from processors.deepseek_client import DeepSeekClient
from prompts.dictionaries import load_all_dictionaries
from prompts.event_prompt import build_event_system_prompt, build_event_user_message
from prompts.schemas import EntityType, EventOutput, HarvestInput

logger = logging.getLogger(__name__)


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

        valid_codes = {
            name: {item["code"] for item in items}
            for name, items in dicts.items()
        }

        cls = result.classification

        for code in cls.thematic_category_codes:
            if code not in valid_codes["thematic_categories"]:
                logger.warning("Invalid thematic_category code: %s in event %s", code, result.title)

        for code in cls.service_codes:
            if code not in valid_codes["services"]:
                logger.warning("Invalid service code: %s in event %s", code, result.title)

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


def to_event_payload(event: EventOutput) -> dict:
    """Конвертация EventOutput → формат для Navigator Core API."""
    return {
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
