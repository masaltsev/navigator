"""
Тесты Pydantic-моделей для полиморфного пайплайна классификации.
Проверяют валидацию, границы значений и round-trip десериализацию.
"""

import pytest
from prompts.schemas import (
    AIConfidenceMetadata,
    EventOutput,
    ExtractedContact,
    OrganizationOutput,
    TaxonomySuggestion,
)


class TestAIConfidenceMetadata:
    def test_valid_accepted(self):
        meta = AIConfidenceMetadata(
            works_with_elderly=True,
            ai_confidence_score=0.95,
            ai_explanation="Гериатрическое отделение, программа 60+",
            decision="accepted",
        )
        assert meta.decision == "accepted"
        assert meta.works_with_elderly is True

    def test_valid_needs_review(self):
        meta = AIConfidenceMetadata(
            works_with_elderly=True,
            ai_confidence_score=0.72,
            ai_explanation="Косвенные признаки работы с пожилыми",
            decision="needs_review",
        )
        assert meta.decision == "needs_review"

    def test_valid_rejected(self):
        meta = AIConfidenceMetadata(
            works_with_elderly=False,
            ai_confidence_score=0.3,
            ai_explanation="Детский сад, нерелевантно",
            decision="rejected",
        )
        assert meta.decision == "rejected"

    def test_invalid_decision_raises(self):
        with pytest.raises(Exception):
            AIConfidenceMetadata(
                works_with_elderly=True,
                ai_confidence_score=0.9,
                ai_explanation="test",
                decision="maybe",
            )

    def test_confidence_score_too_high(self):
        with pytest.raises(Exception):
            AIConfidenceMetadata(
                works_with_elderly=True,
                ai_confidence_score=1.5,
                ai_explanation="test",
                decision="accepted",
            )

    def test_confidence_score_too_low(self):
        with pytest.raises(Exception):
            AIConfidenceMetadata(
                works_with_elderly=True,
                ai_confidence_score=-0.1,
                ai_explanation="test",
                decision="accepted",
            )

    def test_confidence_score_boundaries(self):
        for score in (0.0, 1.0):
            meta = AIConfidenceMetadata(
                works_with_elderly=True,
                ai_confidence_score=score,
                ai_explanation="boundary test",
                decision="accepted",
            )
            assert meta.ai_confidence_score == score


class TestOrganizationOutput:
    VALID_ORG_DATA = {
        "source_reference": "test_1",
        "entity_type": "Organization",
        "title": "Тестовая организация",
        "description": "Описание тестовой организации для проверки схемы.",
        "ai_metadata": {
            "works_with_elderly": True,
            "ai_confidence_score": 0.95,
            "ai_explanation": "Тестовое обоснование.",
            "decision": "accepted",
        },
        "classification": {
            "organization_type_codes": ["141"],
            "ownership_type_code": "154",
            "thematic_category_codes": ["24"],
            "service_codes": ["93"],
            "specialist_profile_codes": [],
        },
        "venues": [],
        "contacts": {"phones": [], "emails": [], "website_urls": []},
        "target_audience": ["elderly"],
        "suggested_taxonomy": [],
    }

    def test_valid_organization_output(self):
        result = OrganizationOutput.model_validate(self.VALID_ORG_DATA)
        assert result.ai_metadata.decision == "accepted"
        assert result.classification.organization_type_codes == ["141"]
        assert result.classification.ownership_type_code == "154"

    def test_optional_fields_default_to_none(self):
        result = OrganizationOutput.model_validate(self.VALID_ORG_DATA)
        assert result.inn is None
        assert result.ogrn is None
        assert result.short_title is None

    def test_idempotency_fields_not_from_llm(self):
        result = OrganizationOutput.model_validate(self.VALID_ORG_DATA)
        assert result.existing_entity_id is None
        assert result.is_update is False

    def test_roundtrip_json(self):
        result = OrganizationOutput.model_validate(self.VALID_ORG_DATA)
        json_str = result.model_dump_json()
        result2 = OrganizationOutput.model_validate_json(json_str)
        assert result == result2

    def test_with_taxonomy_suggestion(self):
        data = {
            **self.VALID_ORG_DATA,
            "suggested_taxonomy": [
                {
                    "target_dictionary": "services",
                    "proposed_name": "Канистерапия",
                    "proposed_description": "Терапия с собаками",
                    "importance_for_elderly": "Снижает тревожность при деменции",
                    "source_text_fragment": "Проводим занятия канистерапии",
                }
            ],
        }
        result = OrganizationOutput.model_validate(data)
        assert len(result.suggested_taxonomy) == 1
        assert result.suggested_taxonomy[0].proposed_name == "Канистерапия"

    def test_with_full_contacts(self):
        data = {
            **self.VALID_ORG_DATA,
            "contacts": {
                "phones": ["+74012555123", "+79001234567"],
                "emails": ["info@org.ru"],
                "website_urls": ["https://org.ru"],
                "vk_url": "https://vk.com/org",
                "ok_url": None,
                "telegram_url": "https://t.me/org",
            },
        }
        result = OrganizationOutput.model_validate(data)
        assert len(result.contacts.phones) == 2
        assert result.contacts.vk_url == "https://vk.com/org"

    def test_multiple_venues(self):
        data = {
            **self.VALID_ORG_DATA,
            "venues": [
                {"address_raw": "ул. Ленина, 1", "address_comment": "1 этаж"},
                {"address_raw": "пр. Мира, 5", "address_comment": None},
            ],
        }
        result = OrganizationOutput.model_validate(data)
        assert len(result.venues) == 2


class TestEventOutput:
    VALID_EVENT_DATA = {
        "source_reference": "event_test_1",
        "entity_type": "Event",
        "title": "Скандинавская ходьба 55+",
        "description": "Бесплатные занятия скандинавской ходьбой.",
        "attendance_mode": "offline",
        "ai_metadata": {
            "works_with_elderly": True,
            "ai_confidence_score": 0.98,
            "ai_explanation": "Маркер 55+, профильная активность",
            "decision": "accepted",
        },
        "classification": {
            "thematic_category_codes": ["24"],
            "service_codes": ["93"],
        },
    }

    def test_valid_event_output(self):
        result = EventOutput.model_validate(self.VALID_EVENT_DATA)
        assert result.title == "Скандинавская ходьба 55+"
        assert result.attendance_mode == "offline"

    def test_event_with_schedule(self):
        data = {
            **self.VALID_EVENT_DATA,
            "schedule": {
                "start_time": "10:00",
                "is_recurring": True,
                "recurrence_description": "каждый вторник и четверг",
                "rrule_suggestion": "FREQ=WEEKLY;BYDAY=TU,TH",
            },
        }
        result = EventOutput.model_validate(data)
        assert result.schedule.is_recurring is True
        assert result.schedule.rrule_suggestion == "FREQ=WEEKLY;BYDAY=TU,TH"


class TestTaxonomySuggestion:
    def test_all_fields_required(self):
        ts = TaxonomySuggestion(
            target_dictionary="services",
            proposed_name="VR-реабилитация",
            proposed_description="Виртуальная реабилитация после инсульта",
            importance_for_elderly="Восстановление моторики и когнитивных функций",
            source_text_fragment="Применяем VR-технологии в реабилитации",
        )
        assert ts.target_dictionary == "services"


class TestExtractedContact:
    def test_defaults_to_empty(self):
        contact = ExtractedContact()
        assert contact.phones == []
        assert contact.emails == []
        assert contact.vk_url is None
