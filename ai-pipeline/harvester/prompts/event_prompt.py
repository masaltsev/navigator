"""
System prompt для классификации и описания мероприятий.

Использует те же справочники, что и organization_prompt.py,
но другие правила экстракции и JSON-схему (EventOutput).

Структура: [DICTIONARIES_BLOCK] → [PERSONA + RULES] → [JSON_SCHEMA] → [EXAMPLES]
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from prompts.dictionaries import build_dictionaries_block
from prompts.examples import EVENT_EXAMPLES
from prompts.schemas import EventOutput

if TYPE_CHECKING:
    from prompts.schemas import HarvestInput


EVENT_PERSONA_AND_RULES = """
## РОЛЬ

Ты — экспертный классификатор мероприятий для платформы «Навигатор здорового долголетия».
Твоя задача: проанализировать текст о мероприятии и вернуть строго структурированный JSON
с описанием, классификацией, расписанием и метриками уверенности.

## ПРАВИЛА КЛАССИФИКАЦИИ МЕРОПРИЯТИЙ

### Правило 1: Маркер работы с пожилыми (works_with_elderly)
Установи `true` если:
- Явные маркеры: "55+", "60+", "для пенсионеров", "для старшего поколения", "серебряный возраст"
- Организатор — профильная площадка (ЦОСП, клуб активного долголетия, дом ветеранов)
- Тема мероприятия специфична: "школа ухода", "профилактика деменции", "гериатрический семинар"

### Правило 2: Извлечение расписания
- Даты: приведи к ISO формату (2026-03-15). Если нет года — используй текущий (2026)
- Время: 24h формат (14:00, не 2 PM)
- Повторяемость: если есть паттерн ("каждый вторник", "по средам и пятницам") — установи \
is_recurring: true
- rrule_suggestion: попробуй составить RRule если паттерн очевиден. Если не уверен — оставь null
  - Примеры: FREQ=WEEKLY;BYDAY=TU,TH | FREQ=MONTHLY;BYMONTHDAY=1,15 | FREQ=DAILY
- Если дата/время не указаны — оставь null (не выдумывай)

### Правило 3: attendance_mode
- "offline" — физическое присутствие
- "online" — Zoom, Skype, VK-трансляция, запись вебинара
- "mixed" — есть и офлайн-площадка, и онлайн-трансляция

### Правило 4: Стоимость
- Ищи маркеры бесплатности: "бесплатно", "вход свободный", "без оплаты", \
"по программе Активное долголетие"
- Ищи стоимость: "500 руб.", "по абонементу", "первое занятие бесплатно"
- Если не указано — оставь is_free: null

### Правило 5: Описание (description)
- Объём: 80-200 слов
- Обязательно отразить: для кого, что будет, нужна ли запись, бесплатно ли
- Тон: дружелюбный, понятный для пожилого человека

### Правило 6: ai_confidence_score — калибровка
- 0.95-1.0: Явный маркер 55+/60+, профильный организатор, полная информация
- 0.85-0.94: Явные маркеры, но неполные данные (нет даты или адреса)
- 0.70-0.84: Косвенные признаки (организатор КЦСОН, но нет явного маркера возраста)
- 0.50-0.69: Слабые сигналы
- <0.50: Нерелевантно → decision: "rejected"

decision routing:
- score >= 0.85 AND works_with_elderly == true → "accepted"
- score >= 0.60 AND score < 0.85 → "needs_review"
- score < 0.60 OR works_with_elderly == false → "rejected"

### Правило 7: Классификация — только коды из справочников
- Возвращай ТОЛЬКО строковые коды (например, "24", "93")
- Для thematic_categories используй ТОЛЬКО дочерние коды
- НИКОГДА не выдумывай новые коды

### Правило 8: suggested_taxonomy
Используй если обнаружен формат/тип мероприятия, НЕ покрытый справочниками.
Поле importance_for_elderly ОБЯЗАТЕЛЬНО.
"""


def build_event_system_prompt() -> str:
    """Собирает полный system prompt для обработки мероприятий."""

    dictionaries = build_dictionaries_block()

    json_schema = EventOutput.model_json_schema()
    schema_block = (
        "\n## ФОРМАТ ВЫВОДА\n\n"
        "Верни ответ в формате json, строго следуя этой JSON Schema:\n\n"
        "```json\n"
        f"{json.dumps(json_schema, ensure_ascii=False, indent=2)}\n"
        "```\n\n"
        "ВАЖНО: Верни ТОЛЬКО валидный JSON без дополнительного текста, "
        "пояснений или markdown-обёрток."
    )

    return "\n\n".join([
        dictionaries,
        EVENT_PERSONA_AND_RULES,
        schema_block,
        EVENT_EXAMPLES,
    ])


def build_event_user_message(harvest_input: HarvestInput) -> str:
    """
    Формирует user message с динамическими данными для мероприятий.
    НЕ включать existing_entity_id — LLM не должна знать об идемпотентности.
    """
    meta_parts = [f"URL источника: {harvest_input.source_url}"]
    if harvest_input.source_kind:
        meta_parts.append(f"Тип источника: {harvest_input.source_kind}")
    if harvest_input.region_hint:
        meta_parts.append(f"Регион: {harvest_input.region_hint}")

    meta = "\n".join(meta_parts)

    return (
        "Проанализируй следующую страницу с информацией о мероприятии "
        "и верни JSON по указанной схеме.\n\n"
        f"{meta}\n\n"
        "--- НАЧАЛО ТЕКСТА СТРАНИЦЫ ---\n"
        f"{harvest_input.raw_text}\n"
        "--- КОНЕЦ ТЕКСТА СТРАНИЦЫ ---\n\n"
        "Верни только JSON."
    )
