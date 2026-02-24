"""
Оркестратор обработки организаций через AI-пайплайн.

Связывает: HarvestInput → System Prompt → DeepSeek API → OrganizationOutput.
Реализует идемпотентность (create / update / mark_outdated) на основе
existing_entity_id, полученного от Harvester до вызова LLM.
"""

import logging
from typing import Callable, Optional

from processors.deepseek_client import DeepSeekClient
from prompts.dictionaries import load_all_dictionaries
from prompts.organization_prompt import (
    build_organization_system_prompt,
    build_organization_user_message,
)
from prompts.schemas import EntityType, HarvestInput, OrganizationOutput

logger = logging.getLogger(__name__)


class OrganizationProcessor:
    """Обрабатывает сырые данные об организации через LLM."""

    def __init__(self, deepseek_client: DeepSeekClient):
        self.client = deepseek_client
        self._system_prompt = build_organization_system_prompt()
        logger.info(
            "Organization system prompt built: ~%d chars", len(self._system_prompt)
        )

    def process(self, harvest_input: HarvestInput) -> OrganizationOutput:
        """
        Классификация одной организации через LLM.

        Поля existing_entity_id / is_update устанавливаются отдельно
        в process_and_sync (LLM не знает об идемпотентности).
        """
        assert harvest_input.entity_type == EntityType.ORGANIZATION

        user_message = build_organization_user_message(harvest_input)

        result = self.client.classify(
            system_prompt=self._system_prompt,
            user_message=user_message,
            output_model=OrganizationOutput,
        )

        result.source_reference = harvest_input.source_item_id
        self._validate_codes(result)

        return result

    def _validate_codes(self, result: OrganizationOutput) -> None:
        """
        Post-hoc проверка и автокоррекция кодов справочников.

        Типичная ошибка LLM: путает organization_type и ownership_type коды.
        Если код org_type найден в ownership_types — переносим его.
        """
        dicts = load_all_dictionaries()

        valid_codes = {
            name: {item["code"] for item in items}
            for name, items in dicts.items()
        }

        cls = result.classification

        corrected_org_types: list[str] = []
        for code in cls.organization_type_codes:
            if code in valid_codes["organization_types"]:
                corrected_org_types.append(code)
            elif code in valid_codes["ownership_types"]:
                if not cls.ownership_type_code:
                    cls.ownership_type_code = code
                    logger.info(
                        "Auto-corrected: moved code %s from org_type → ownership_type in %s",
                        code, result.title,
                    )
                else:
                    logger.warning(
                        "Dropped misplaced ownership code %s from org_type_codes "
                        "(ownership already set to %s) in %s",
                        code, cls.ownership_type_code, result.title,
                    )
            else:
                logger.warning("Invalid organization_type code: %s in %s", code, result.title)
        cls.organization_type_codes = corrected_org_types

        if cls.ownership_type_code:
            if cls.ownership_type_code in valid_codes["ownership_types"]:
                pass
            elif cls.ownership_type_code in valid_codes["organization_types"]:
                cls.organization_type_codes.append(cls.ownership_type_code)
                cls.ownership_type_code = None
                logger.info(
                    "Auto-corrected: moved ownership_type_code → org_type_codes in %s",
                    result.title,
                )
            else:
                logger.warning(
                    "Invalid ownership_type code: %s in %s",
                    cls.ownership_type_code, result.title,
                )

        for code in cls.thematic_category_codes:
            if code not in valid_codes["thematic_categories"]:
                logger.warning("Invalid thematic_category code: %s in %s", code, result.title)

        for code in cls.service_codes:
            if code not in valid_codes["services"]:
                logger.warning("Invalid service code: %s in %s", code, result.title)

        for code in cls.specialist_profile_codes:
            if code not in valid_codes["specialist_profiles"]:
                logger.warning("Invalid specialist_profile code: %s in %s", code, result.title)

    # ------------------------------------------------------------------
    # Idempotency routing
    # ------------------------------------------------------------------

    def process_and_sync(self, harvest_input: HarvestInput) -> dict:
        """
        Полный цикл: LLM → Pydantic → решение CREATE / UPDATE / OUTDATED.

        existing_entity_id приходит из HarvestInput (Harvester определяет
        его ДО вызова LLM через GET /api/internal/organizers?source_id=X&source_item_id=Y).
        """
        org = self.process(harvest_input)

        org.existing_entity_id = harvest_input.existing_entity_id
        org.is_update = harvest_input.existing_entity_id is not None

        decision = org.ai_metadata.decision

        if decision == "rejected":
            if org.is_update:
                return self._mark_as_outdated(org.existing_entity_id, org)  # type: ignore[arg-type]
            return {"action": "skipped", "reason": "rejected_new"}

        if decision == "accepted":
            if org.is_update:
                return self._update_organizer(org)
            return self._create_organizer(org)

        # needs_review
        if org.is_update:
            return self._update_organizer_with_review(org)
        return self._create_draft(org)

    def _create_organizer(self, result: OrganizationOutput) -> dict:
        payload = to_core_import_payload(result)
        payload["action"] = "create"
        return {"action": "created", "payload": payload}

    def _update_organizer(self, result: OrganizationOutput) -> dict:
        payload = to_core_import_payload(result)
        payload["action"] = "update"
        payload["existing_entity_id"] = result.existing_entity_id
        return {"action": "updated", "payload": payload}

    def _update_organizer_with_review(self, result: OrganizationOutput) -> dict:
        payload = to_core_import_payload(result)
        payload["action"] = "update"
        payload["existing_entity_id"] = result.existing_entity_id
        payload["requires_review"] = True
        return {"action": "updated_needs_review", "payload": payload}

    def _create_draft(self, result: OrganizationOutput) -> dict:
        payload = to_core_import_payload(result)
        payload["action"] = "create_draft"
        return {"action": "created_draft", "payload": payload}

    def _mark_as_outdated(self, entity_id: str, result: OrganizationOutput) -> dict:
        return {
            "action": "mark_outdated",
            "existing_entity_id": entity_id,
            "ai_explanation": result.ai_metadata.ai_explanation,
        }

    # ------------------------------------------------------------------
    # Batch processing
    # ------------------------------------------------------------------

    def process_batch(
        self,
        items: list[HarvestInput],
        on_success: Optional[Callable] = None,
        on_error: Optional[Callable] = None,
    ) -> list[dict]:
        """
        Последовательная обработка пакета организаций.
        System prompt при этом ОДИН — максимальный cache hit.
        """
        results: list[dict] = []
        for i, item in enumerate(items):
            try:
                result = self.process_and_sync(item)
                results.append(result)
                if on_success:
                    on_success(i, result)
            except Exception as e:
                logger.error("Failed to process %s: %s", item.source_item_id, e)
                if on_error:
                    on_error(i, item, e)

        metrics = self.client.get_metrics()
        logger.info(
            "Batch complete: %d/%d successful. Cache hit rate: %.1f%%. Est. cost: $%.4f",
            len(results),
            len(items),
            metrics["cache_hit_rate"] * 100,
            metrics["estimated_cost_usd"],
        )

        return results


# ---------------------------------------------------------------------------
# Core API payload conversion
# ---------------------------------------------------------------------------


def to_core_import_payload(org: OrganizationOutput) -> dict:
    """Конвертация OrganizationOutput → формат POST /api/internal/import/organizer."""
    return {
        "source_reference": org.source_reference,
        "entity_type": "Organization",
        "title": org.title,
        "short_title": org.short_title,
        "description": org.description,
        "inn": org.inn,
        "ogrn": org.ogrn,
        "ai_metadata": {
            "decision": org.ai_metadata.decision,
            "ai_explanation": org.ai_metadata.ai_explanation,
            "ai_confidence_score": org.ai_metadata.ai_confidence_score,
            "works_with_elderly": org.ai_metadata.works_with_elderly,
        },
        "classification": {
            "organization_type_codes": org.classification.organization_type_codes,
            "ownership_type_code": org.classification.ownership_type_code,
            "thematic_category_codes": org.classification.thematic_category_codes,
            "service_codes": org.classification.service_codes,
            "specialist_profile_codes": org.classification.specialist_profile_codes,
        },
        "venues": [
            {"address_raw": v.address_raw, "address_comment": v.address_comment}
            for v in org.venues
        ],
        "contacts": {
            "phones": org.contacts.phones,
            "emails": org.contacts.emails,
        },
        "site_urls": org.contacts.website_urls,
        "vk_group_url": org.contacts.vk_url,
        "ok_group_url": org.contacts.ok_url,
        "telegram_url": org.contacts.telegram_url,
        "target_audience": org.target_audience,
        "suggested_taxonomy": [s.model_dump() for s in org.suggested_taxonomy],
    }
