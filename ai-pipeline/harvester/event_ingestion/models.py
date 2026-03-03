"""
Каноническая модель ввода мероприятия из любого источника.

Все источники (Silver Age, обход сайта организации, соцсети, будущие агрегаторы)
должны преобразовывать свои данные в RawEventInput. Так пайплайн получает
единую структуру и качество контента перед классификацией и отправкой в Core.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=False)
class RawEventInput:
    """
    Единый вход пайплайна приёма мероприятий.

    Обязательные поля для любого источника:
      - source_reference: уникальный идентификатор (для дедупа в Core)
      - title: название мероприятия
      - raw_text: текст для LLM (описание, markdown страницы, пост — всё, что нужно для классификации)
      - source_url: URL страницы/поста мероприятия (сохраняется в event_page_url и ai_source_trace)
      - source_kind: тип источника (см. SOURCE_KINDS)

    Остальные поля опциональны; пайплайн и LLM могут восполнить их.
    """

    source_reference: str
    title: str
    raw_text: str
    source_url: str
    source_kind: str

    # Даты: либо уже в ISO, либо date_text для парсинга
    date_text: Optional[str] = None
    start_datetime_iso: Optional[str] = None
    end_datetime_iso: Optional[str] = None

    location: Optional[str] = None
    is_online: bool = False
    registration_url: Optional[str] = None
    category_from_source: Optional[str] = None  # категория на стороне источника
    region_hint: Optional[str] = None

    # Для трассировки: откуда пришло (например base_url сайта или id агрегатора)
    discovered_from: Optional[str] = None


# Рекомендуемые значения source_kind для единообразия
SOURCE_KIND_AGGREGATOR_SILVERAGE = "platform_silverage"
SOURCE_KIND_ORG_WEBSITE = "org_website"
SOURCE_KIND_VK = "vk_group"
SOURCE_KIND_TELEGRAM = "tg_channel"
# При добавлении новых — завести константу и использовать в адаптере
