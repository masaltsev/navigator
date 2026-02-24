"""
Pydantic v2 models for the polymorphic classification pipeline.

Defines the contract between:
  - Harvester (input: HarvestInput)
  - LLM / DeepSeek API (output: OrganizationOutput / EventOutput)
  - Navigator Core API (via to_core_import_payload conversion)

These models are SEPARATE from schemas/extraction.py (Crawl4AI free-form extraction)
and schemas/navigator_core.py (Core API payload). They serve the direct DeepSeek
classification pipeline with schema-constrained output.
"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Input
# ---------------------------------------------------------------------------

class EntityType(str, Enum):
    ORGANIZATION = "Organization"
    EVENT = "Event"


class HarvestInput(BaseModel):
    """Входные данные от Harvester для обработки ИИ."""

    source_id: str = Field(description="UUID источника из таблицы sources")
    source_item_id: str = Field(
        description="Уникальный ID элемента внутри источника (URL slug, API id, registry entry_id)"
    )
    entity_type: EntityType
    raw_text: str = Field(description="Очищенный от HTML текст страницы (через Crawl4AI/Firecrawl)")
    source_url: str = Field(description="URL исходной страницы")
    source_kind: Optional[str] = Field(
        default=None,
        description=(
            "Тип источника: registry_sfr, registry_minsoc, "
            "org_website, vk_group, tg_channel, api_json"
        ),
    )
    region_hint: Optional[str] = Field(
        default=None,
        description="ISO-код региона, если известен из источника (e.g., 'RU-KGD')",
    )
    existing_entity_id: Optional[str] = Field(
        default=None,
        description=(
            "UUID существующей записи organizer/event в Navigator Core, "
            "если по (source_id, source_item_id) уже найдена сущность. "
            "Используется для идемпотентности."
        ),
    )


# ---------------------------------------------------------------------------
# Shared blocks
# ---------------------------------------------------------------------------

class AIConfidenceMetadata(BaseModel):
    """Метаданные уверенности ИИ — общий блок для Organization и Event."""

    works_with_elderly: bool = Field(
        description="True если ≥1 услуга/отделение/специалист явно ориентирован на людей 55+"
    )
    ai_confidence_score: float = Field(
        ge=0.0,
        le=1.0,
        description="Вероятность корректности классификации (0.0-1.0)",
    )
    ai_explanation: str = Field(
        description="Обоснование решения, 2-4 предложения. Упомянуть конкретные маркеры из текста."
    )
    decision: str = Field(description="accepted | rejected | needs_review")

    @field_validator("decision")
    @classmethod
    def validate_decision(cls, v: str) -> str:
        allowed = ("accepted", "rejected", "needs_review")
        if v not in allowed:
            raise ValueError(f"decision must be one of {allowed}, got '{v}'")
        return v


class ExtractedVenue(BaseModel):
    """Извлечённый адрес площадки."""

    address_raw: str = Field(description="Адрес как найден в тексте")
    address_comment: Optional[str] = Field(
        default=None,
        description="Уточнение: этаж, кабинет, корпус",
    )


class ExtractedContact(BaseModel):
    """Извлечённые контакты."""

    phones: list[str] = Field(default_factory=list, description="Телефоны в формате +7XXXXXXXXXX")
    emails: list[str] = Field(default_factory=list)
    website_urls: list[str] = Field(default_factory=list)
    vk_url: Optional[str] = None
    ok_url: Optional[str] = None
    telegram_url: Optional[str] = None


class TaxonomySuggestion(BaseModel):
    """Предложение нового термина для справочника."""

    target_dictionary: str = Field(
        description=(
            "Имя справочника: services | organization_types | "
            "thematic_categories | specialist_profiles"
        )
    )
    proposed_name: str = Field(description="Краткое название предлагаемого термина")
    proposed_description: str = Field(description="Описание в 1-2 предложения")
    importance_for_elderly: str = Field(
        description="Обоснование значимости для пожилых людей, 1-2 предложения"
    )
    source_text_fragment: str = Field(
        description="Цитата из исходного текста, подтверждающая обнаружение"
    )


# ---------------------------------------------------------------------------
# Organization output
# ---------------------------------------------------------------------------

class OrganizationClassification(BaseModel):
    """Классификация организации по справочникам (только коды)."""

    organization_type_codes: list[str] = Field(
        description="Коды из organization_types.json (M:N). Например: ['141', '82']"
    )
    ownership_type_code: Optional[str] = Field(
        default=None,
        description="Код из ownership_types.json (1:1). Например: '154'",
    )
    thematic_category_codes: list[str] = Field(
        description="Коды ДОЧЕРНИХ категорий из thematic_categories.json. Например: ['7', '24']"
    )
    service_codes: list[str] = Field(
        description="Коды из services.json (M:N). Например: ['70', '75', '91']"
    )
    specialist_profile_codes: list[str] = Field(
        default_factory=list,
        description="Коды из specialist_profiles.json (M:N). Например: ['143', '142']",
    )


class OrganizationOutput(BaseModel):
    """Полная выходная структура для организации."""

    source_reference: str = ""
    existing_entity_id: Optional[str] = Field(
        default=None,
        description="UUID существующей записи organizer, если это обновление (не передаётся в LLM)",
    )
    is_update: bool = Field(
        default=False,
        description="True если Harvester обнаружил существующую запись (не передаётся в LLM)",
    )
    entity_type: str = "Organization"

    title: str = Field(description="Официальное название организации")
    short_title: Optional[str] = Field(
        default=None,
        description="Короткое название для UI (если официальное > 80 символов)",
    )
    description: str = Field(
        description=(
            "SEO-описание 150-300 слов для карточки на сайте. "
            "Тон: информативный, без канцелярита."
        )
    )
    inn: Optional[str] = Field(default=None, description="ИНН (10 или 12 цифр)")
    ogrn: Optional[str] = Field(default=None, description="ОГРН (13 или 15 цифр)")

    ai_metadata: AIConfidenceMetadata
    classification: OrganizationClassification
    venues: list[ExtractedVenue] = Field(default_factory=list)
    contacts: ExtractedContact = Field(default_factory=ExtractedContact)
    target_audience: list[str] = Field(
        default_factory=list,
        description="Массив из: 'elderly', 'relatives', 'specialists', 'youth_intergenerational'",
    )
    suggested_taxonomy: list[TaxonomySuggestion] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Event output
# ---------------------------------------------------------------------------

class EventSchedule(BaseModel):
    """Извлечённое расписание мероприятия."""

    start_date: Optional[str] = Field(default=None, description="ISO date: 2026-03-15")
    end_date: Optional[str] = Field(default=None, description="ISO date: 2026-03-15")
    start_time: Optional[str] = Field(default=None, description="HH:MM в 24h формате")
    end_time: Optional[str] = Field(default=None, description="HH:MM")
    is_recurring: bool = Field(default=False)
    recurrence_description: Optional[str] = Field(
        default=None,
        description="Текстовое описание повторяемости: 'каждый вторник и четверг', 'по средам'",
    )
    rrule_suggestion: Optional[str] = Field(
        default=None,
        description="Предложенная RRule строка: FREQ=WEEKLY;BYDAY=TU,TH",
    )


class EventClassification(BaseModel):
    """Классификация мероприятия."""

    event_category_codes: list[str] = Field(
        default_factory=list,
        description="Коды категорий мероприятий (если справочник event_categories предоставлен)",
    )
    thematic_category_codes: list[str] = Field(
        description="Коды дочерних тематических категорий"
    )
    service_codes: list[str] = Field(description="Коды связанных услуг из services.json")


class EventOutput(BaseModel):
    """Полная выходная структура для мероприятия."""

    source_reference: str = ""
    existing_entity_id: Optional[str] = Field(
        default=None,
        description="UUID существующего event, если это обновление (не передаётся в LLM)",
    )
    is_update: bool = Field(
        default=False,
        description="Флаг повторной обработки (не передаётся в LLM)",
    )
    entity_type: str = "Event"

    title: str = Field(description="Название мероприятия")
    description: str = Field(
        description="Описание 80-200 слов. Включить: для кого, что будет, нужна ли запись."
    )
    attendance_mode: str = Field(description="offline | online | mixed")
    online_url: Optional[str] = Field(default=None, description="Ссылка на онлайн-трансляцию")
    is_free: Optional[bool] = Field(default=None, description="Бесплатно ли мероприятие")
    price_description: Optional[str] = Field(
        default=None,
        description="Описание стоимости, если не бесплатно",
    )
    registration_required: Optional[bool] = Field(default=None)
    registration_url: Optional[str] = None

    organizer_title: Optional[str] = Field(
        default=None,
        description="Название организации-организатора, если найдено в тексте",
    )
    organizer_inn: Optional[str] = None

    schedule: EventSchedule = Field(default_factory=EventSchedule)
    ai_metadata: AIConfidenceMetadata
    classification: EventClassification
    venues: list[ExtractedVenue] = Field(default_factory=list)
    contacts: ExtractedContact = Field(default_factory=ExtractedContact)
    target_audience: list[str] = Field(default_factory=list)
    age_restriction: Optional[str] = Field(
        default=None,
        description="Возрастное ограничение: '55+', '60+', 'без ограничений'",
    )
    suggested_taxonomy: list[TaxonomySuggestion] = Field(default_factory=list)
