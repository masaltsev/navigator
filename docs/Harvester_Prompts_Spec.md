# Спецификация полиморфных промптов Harvester v1 — Navigator AI Pipeline

> **Версия:** 1.1 final · **Дата:** 2026-02-22
> **Назначение:** Практическая спецификация для реализации в Cursor AI.
> **Связанные документы:** `harvester_v1_prompt.md` (архитектурный контекст, read-only).

***

## 2.0. Контекст и цели

Данная спецификация предназначена для AI-агентов Cursor IDE. Цель — реализовать Python-модуль системы промптов для автоматической классификации и описания организаций и мероприятий для платформы «Навигатор здорового долголетия».

**Технический стек:**
- Python 3.11+
- Pydantic v2 для валидации ввода/вывода
- DeepSeek API (V3 или R1) через OpenAI-compatible SDK
- JSON-справочники как единый источник истины (seeders)

**Прмерная файловая структура целевого модуля (опирайся на сложившуюся в репозитории, без необходимости не переписывай):**

```
harvester/
├── prompts/
│   ├── __init__.py
│   ├── base.py                    # Базовые абстракции, сборка промптов
│   ├── dictionaries.py            # Загрузка и форматирование справочников
│   ├── organization_prompt.py     # Промпт для организаций
│   ├── event_prompt.py            # Промпт для мероприятий
│   ├── examples.py                # Few-shot примеры
│   └── schemas.py                 # Pydantic-модели ввода/вывода
├── processors/
│   ├── __init__.py
│   ├── organization_processor.py  # Оркестрация обработки организаций
│   ├── event_processor.py         # Оркестрация обработки мероприятий
│   └── deepseek_client.py         # Клиент DeepSeek API
├── seeder_data/                  # JSON-файлы справочников
│   ├── ownership_types.json
│   ├── organization_types.json
│   ├── services.json
│   ├── specialist_profiles.json
│   └── thematic_categories.json
└── tests/
    ├── test_prompts.py
    ├── test_schemas.py
    └── fixtures/                  # Примеры raw_html для тестов
```

***

## 2.1. Pydantic-схемы (`schemas.py`)

### 2.1.1. Входные модели

```python
from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


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
        description="Тип источника: registry_sfr, registry_minsoc, org_website, vk_group, tg_channel, api_json"
    )
    region_hint: Optional[str] = Field(
        default=None,
        description="ISO-код региона, если известен из источника (e.g., 'RU-KGD')"
    )
    existing_entity_id: Optional[str] = Field(
        default=None,
        description=(
            "UUID существующей записи organizer/event в Navigator Core, "
            "если по (source_id, source_item_id) уже найдена сущность. "
            "Используется для идемпотентности — см. раздел 2.12."
        )
    )
```

### 2.1.2. Общие блоки (уверенность, контакты, площадки, таксономия)

```python
class AIConfidenceMetadata(BaseModel):
    """Метаданные уверенности ИИ — общий блок."""
    works_with_elderly: bool = Field(
        description="True если ≥1 услуга/отделение/специалист явно ориентирован на людей 55+"
    )
    ai_confidence_score: float = Field(
        ge=0.0, le=1.0,
        description="Вероятность корректности классификации (0.0-1.0)"
    )
    ai_explanation: str = Field(
        description="Обоснование решения, 2-4 предложения. Упомянуть конкретные маркеры из текста."
    )
    decision: str = Field(
        description="accepted | rejected | needs_review"
    )

    @field_validator("decision")
    @classmethod
    def validate_decision(cls, v):
        if v not in ("accepted", "rejected", "needs_review"):
            raise ValueError("decision must be 'accepted', 'rejected', or 'needs_review'")
        return v


class ExtractedVenue(BaseModel):
    """Извлечённый адрес площадки."""
    address_raw: str = Field(description="Адрес как найден в тексте")
    address_comment: Optional[str] = Field(
        default=None,
        description="Уточнение: этаж, кабинет, корпус"
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
        description="Имя справочника: services | organization_types | thematic_categories | specialist_profiles"
    )
    proposed_name: str = Field(description="Краткое название предлагаемого термина")
    proposed_description: str = Field(description="Описание в 1-2 предложения")
    importance_for_elderly: str = Field(
        description="Обоснование значимости для пожилых людей, 1-2 предложения"
    )
    source_text_fragment: str = Field(
        description="Цитата из исходного текста, подтверждающая обнаружение"
    )
```

### 2.1.3. Выходные модели: Организация

```python
class OrganizationClassification(BaseModel):
    """Классификация организации по справочникам (только коды)."""
    organization_type_codes: list[str] = Field(
        description="Коды из organization_types.json (M:N). Например: ['141', '82']"
    )
    ownership_type_code: Optional[str] = Field(
        default=None,
        description="Код из ownership_types.json (1:1). Например: '154'"
    )
    thematic_category_codes: list[str] = Field(
        description="Коды ДОЧЕРНИХ категорий из thematic_categories.json. Например: ['7', '24']"
    )
    service_codes: list[str] = Field(
        description="Коды из services.json (M:N). Например: ['70', '75', '91']"
    )
    specialist_profile_codes: list[str] = Field(
        default_factory=list,
        description="Коды из specialist_profiles.json (M:N). Например: ['143', '142']"
    )


class OrganizationOutput(BaseModel):
    """Полная выходная структура для организации."""
    # Идентификация и идемпотентность
    source_reference: str
    existing_entity_id: Optional[str] = Field(
        default=None,
        description="UUID существующей записи organizer, если это обновление (не передаётся в LLM)"
    )
    is_update: bool = Field(
        default=False,
        description="True если Harvester обнаружил существующую запись (не передаётся в LLM)"
    )
    entity_type: str = "Organization"
    
    # Основные данные
    title: str = Field(description="Официальное название организации")
    short_title: Optional[str] = Field(
        default=None,
        description="Короткое название для UI (если официальное > 80 символов)"
    )
    description: str = Field(
        description="SEO-описание 150-300 слов для карточки на сайте. Тон: информативный, без канцелярита."
    )
    inn: Optional[str] = Field(default=None, description="ИНН (10 или 12 цифр)")
    ogrn: Optional[str] = Field(default=None, description="ОГРН (13 или 15 цифр)")
    
    # Метаданные ИИ
    ai_metadata: AIConfidenceMetadata
    
    # Классификация
    classification: OrganizationClassification
    
    # Площадки
    venues: list[ExtractedVenue] = Field(default_factory=list)
    
    # Контакты
    contacts: ExtractedContact = Field(default_factory=ExtractedContact)
    
    # Целевая аудитория
    target_audience: list[str] = Field(
        default_factory=list,
        description="Массив из: 'elderly', 'relatives', 'specialists', 'youth_intergenerational'"
    )
    
    # Расширение таксономии
    suggested_taxonomy: list[TaxonomySuggestion] = Field(default_factory=list)
```

### 2.1.4. Выходные модели: Мероприятие

```python
class EventSchedule(BaseModel):
    """Извлечённое расписание мероприятия."""
    start_date: Optional[str] = Field(default=None, description="ISO date: 2026-03-15")
    end_date: Optional[str] = Field(default=None, description="ISO date: 2026-03-15")
    start_time: Optional[str] = Field(default=None, description="HH:MM в 24h формате")
    end_time: Optional[str] = Field(default=None, description="HH:MM")
    is_recurring: bool = Field(default=False)
    recurrence_description: Optional[str] = Field(
        default=None,
        description="Текстовое описание повторяемости: 'каждый вторник и четверг', 'по средам'"
    )
    rrule_suggestion: Optional[str] = Field(
        default=None,
        description="Предложенная RRule строка, если возможно вычислить: FREQ=WEEKLY;BYDAY=TU,TH"
    )


class EventClassification(BaseModel):
    """Классификация мероприятия."""
    event_category_codes: list[str] = Field(
        default_factory=list,
        description="Коды категорий мероприятий (если справочник event_categories предоставлен)"
    )
    thematic_category_codes: list[str] = Field(
        description="Коды дочерних тематических категорий"
    )
    service_codes: list[str] = Field(
        description="Коды связанных услуг из services.json"
    )


class EventOutput(BaseModel):
    """Полная выходная структура для мероприятия."""
    # Идентификация и идемпотентность
    source_reference: str
    existing_entity_id: Optional[str] = Field(
        default=None,
        description="UUID существующего event, если это обновление (не передаётся в LLM)"
    )
    is_update: bool = Field(
        default=False,
        description="Флаг повторной обработки (не передаётся в LLM)"
    )
    entity_type: str = "Event"
    
    # Основные данные
    title: str = Field(description="Название мероприятия")
    description: str = Field(
        description="Описание 80-200 слов. Включить: для кого, что будет, нужна ли запись."
    )
    attendance_mode: str = Field(
        description="offline | online | mixed"
    )
    online_url: Optional[str] = Field(default=None, description="Ссылка на онлайн-трансляцию")
    is_free: Optional[bool] = Field(default=None, description="Бесплатно ли мероприятие")
    price_description: Optional[str] = Field(
        default=None,
        description="Описание стоимости, если не бесплатно"
    )
    registration_required: Optional[bool] = Field(default=None)
    registration_url: Optional[str] = None
    
    # Связь с организатором
    organizer_title: Optional[str] = Field(
        default=None,
        description="Название организации-организатора, если найдено в тексте"
    )
    organizer_inn: Optional[str] = None
    
    # Расписание
    schedule: EventSchedule = Field(default_factory=EventSchedule)
    
    # Метаданные ИИ
    ai_metadata: AIConfidenceMetadata
    
    # Классификация
    classification: EventClassification
    
    # Площадки
    venues: list[ExtractedVenue] = Field(default_factory=list)
    
    # Контакты
    contacts: ExtractedContact = Field(default_factory=ExtractedContact)
    
    # Целевая аудитория
    target_audience: list[str] = Field(default_factory=list)
    age_restriction: Optional[str] = Field(
        default=None,
        description="Возрастное ограничение: '55+', '60+', 'без ограничений'"
    )
    
    # Расширение таксономии
    suggested_taxonomy: list[TaxonomySuggestion] = Field(default_factory=list)
```

***

## 2.2. Модуль загрузки справочников (`dictionaries.py`)

```python
"""
Загрузка и форматирование справочников для инжекции в system prompt.
КРИТИЧНО: порядок и формат блоков влияют на cache hit rate DeepSeek.
"""
import json
from pathlib import Path
from functools import lru_cache


DICT_DIR = Path(__file__).parent.parent / "dictionaries"

# Порядок загрузки — ФИКСИРОВАННЫЙ (влияет на prefix caching)
DICTIONARY_LOAD_ORDER = [
    "thematic_categories",
    "organization_types", 
    "services",
    "specialist_profiles",
    "ownership_types",
]


@lru_cache(maxsize=1)
def load_all_dictionaries() -> dict[str, list[dict]]:
    """Загрузка всех справочников в memory. Кэшируется на уровне процесса."""
    result = {}
    for name in DICTIONARY_LOAD_ORDER:
        file_path = DICT_DIR / f"{name}.json"
        with open(file_path, "r", encoding="utf-8") as f:
            result[name] = json.load(f)
    return result


def format_dictionary_for_prompt(name: str, items: list[dict]) -> str:
    """
    Форматирует справочник в компактный текстовый блок для system prompt.
    
    Формат оптимизирован для:
    1. Минимизации токенов (убираем is_active, id — модели нужен только code)
    2. Максимизации семантической связности (keywords inline)
    3. Для thematic_categories — показываем иерархию
    """
    lines = [f"### СПРАВОЧНИК: {name.upper()}"]
    
    if name == "thematic_categories":
        # Группируем по parent_code для иерархии
        parents = {item["code"]: item for item in items if item.get("parent_code") is None}
        children = [item for item in items if item.get("parent_code") is not None]
        
        for p_code, parent in sorted(parents.items(), key=lambda x: x):
            lines.append(f"\n#### {parent['name']} (родительский код: {p_code})")
            lines.append(f"  Описание: {parent['description']}")
            lines.append(f"  Ключевые слова: {', '.join(parent['keywords'])}")
            
            for child in sorted(children, key=lambda x: x["code"]):
                if child.get("parent_code") == p_code:
                    kw = ", ".join(child["keywords"])
                    lines.append(
                        f"  - код \"{child['code']}\": {child['name']} "
                        f"| {child['description']} "
                        f"| keywords: [{kw}]"
                    )
    else:
        for item in sorted(items, key=lambda x: x["code"]):
            kw = ", ".join(item.get("keywords", []))
            desc = item.get("description", "")
            lines.append(
                f"- код \"{item['code']}\": {item['name']} "
                f"| {desc} "
                f"| keywords: [{kw}]"
            )
    
    return "\n".join(lines)


@lru_cache(maxsize=1)
def build_dictionaries_block() -> str:
    """
    Собирает полный блок справочников для system prompt.
    
    ВАЖНО: Этот блок ДОЛЖЕН быть ПЕРВЫМ в system prompt
    для максимизации prefix cache hit rate в DeepSeek API.
    Блок является ПОЛНОСТЬЮ СТАТИЧНЫМ — никаких переменных.
    """
    dicts = load_all_dictionaries()
    blocks = []
    
    blocks.append("=" * 60)
    blocks.append("ЗАКРЫТЫЕ СПРАВОЧНИКИ ПЛАТФОРМЫ «НАВИГАТОР ЗДОРОВОГО ДОЛГОЛЕТИЯ»")
    blocks.append("Используй ТОЛЬКО коды из этих справочников для классификации.")
    blocks.append("НЕ ВЫДУМЫВАЙ новые коды. Для неизвестных терминов используй suggested_taxonomy.")
    blocks.append("=" * 60)
    
    for name in DICTIONARY_LOAD_ORDER:
        blocks.append(format_dictionary_for_prompt(name, dicts[name]))
    
    blocks.append("=" * 60)
    blocks.append("КОНЕЦ СПРАВОЧНИКОВ")
    blocks.append("=" * 60)
    
    return "\n\n".join(blocks)
```

***

## 2.3. Текст системного промпта: Организации (`organization_prompt.py`)

```python
"""
System prompt для классификации и описания организаций.
Структура оптимизирована для DeepSeek prefix caching:
  [DICTIONARIES_BLOCK] → [PERSONA] → [RULES] → [JSON_SCHEMA] → [EXAMPLES]
"""
import json
from .dictionaries import build_dictionaries_block
from .schemas import OrganizationOutput
from .examples import ORGANIZATION_EXAMPLES


def build_organization_system_prompt() -> str:
    """Собирает полный system prompt для обработки организаций."""
    
    # ═══════════════════════════════════════════
    # БЛОК 1: СПРАВОЧНИКИ (статичный, кэшируемый)
    # ═══════════════════════════════════════════
    dictionaries = build_dictionaries_block()
    
    # ═══════════════════════════════════════════
    # БЛОК 2: ПЕРСОНА И ПРАВИЛА (статичный)
    # ═══════════════════════════════════════════
    persona_and_rules = """
## РОЛЬ

Ты — экспертный классификатор организаций для платформы «Навигатор здорового долголетия».
Твоя задача: проанализировать текст веб-страницы организации и вернуть строго структурированный JSON
с описанием, классификацией по справочникам и метриками уверенности.

## ПРАВИЛА КЛАССИФИКАЦИИ

### Правило 1: Маркер работы с пожилыми (works_with_elderly)
Установи `true` если выполняется ХОТЯ БЫ ОДНО условие:
- В тексте есть явные маркеры: "55+", "60+", "пенсионеры", "старшее поколение", "пожилые", "серебряный возраст", "активное долголетие", "московское долголетие", "ветераны"
- Организация имеет профильные отделения: гериатрическое, паллиативное, геронтопсихиатрическое
- В штате есть профильные специалисты: гериатр, геронтопсихолог, геронтопсихиатр
- Организация является КЦСОН, ПНИ, домом престарелых, хосписом (по своей природе работает с пожилыми)
- Предоставляются специфические услуги: сиделка, дневной уход, долговременный уход (СДУ), прокат ТСР

НЕ УСТАНАВЛИВАЙ `true` только на основании:
- Общемедицинского характера организации (поликлиника без гериатрического фокуса)
- Наличия общих социальных услуг без указания на старшее поколение
- Упоминания детей, молодёжи или общей аудитории без явного указания на пожилых

### Правило 2: Полиморфная маршрутизация (фокус внимания)
В зависимости от типа организации СМЕСТИ ФОКУС экстракции:

**ПАТТЕРН A — Медицинские учреждения** (ГБУ, ГБУЗ, поликлиника, больница, диспансер, реабцентр):
- ПРИОРИТЕТ: извлечь специалистов (specialist_profile_codes), медицинские услуги
- ИСКАТЬ: гериатрическое отделение, кабинет/клинику памяти, паллиативное отделение
- ОПРЕДЕЛИТЬ: платные vs бесплатные (ОМС) услуги — указать в описании
- ИГНОРИРОВАТЬ: общие педиатрические, акушерские услуги (нерелевантны)

**ПАТТЕРН B — Социальная защита** (КЦСОН, ПНИ, интернат, кризисный центр, соцзащита):
- ПРИОРИТЕТ: извлечь формы помощи (надомное обслуживание, патронаж, СДУ)
- ИСКАТЬ: юридические консультации, прокат ТСР, группы дневного пребывания
- ОПРЕДЕЛИТЬ: условия предоставления услуг (категории получателей)
- ОБРАТИТЬ ВНИМАНИЕ: нуждаемость в уходе (код 18), одинокое проживание (код 20)

**ПАТТЕРН C — Активное долголетие** (ЦОСП, досуговый центр, клуб, ДК, библиотека):
- ПРИОРИТЕТ: извлечь конкретные занятия, кружки, расписание
- ИСКАТЬ: скандинавская ходьба, хор, рисование, компьютерные курсы, йога
- ОПРЕДЕЛИТЬ: бесплатность, возрастной ценз, необходимость записи
- ОБЯЗАТЕЛЬНО: подтвердить наличие маркера "55+" / "для пенсионеров"

### Правило 3: Классификация — только коды из справочников
- Возвращай ТОЛЬКО строковые коды из предоставленных справочников (например, "141", "82")
- НИКОГДА не выдумывай новые коды
- Для thematic_categories используй ТОЛЬКО дочерние коды (с parent_code != null)
- Если термин не мапится ни на один код — добавь в suggested_taxonomy

### Правило 4: ai_confidence_score — калибровка
- 0.95-1.0: Прямое упоминание работы с пожилыми + профильные услуги/специалисты + ИНН/ОГРН найдены
- 0.85-0.94: Явные маркеры старшего возраста, но не все данные подтверждены
- 0.70-0.84: Косвенные признаки (КЦСОН без явного упоминания пожилых, общий реабцентр)
- 0.50-0.69: Слабые сигналы, требуется ручная проверка
- <0.50: Скорее нерелевантная организация — установи decision: "rejected"

decision routing:
- score >= 0.85 AND works_with_elderly == true → "accepted" 
- score >= 0.60 AND score < 0.85 → "needs_review"
- score < 0.60 OR works_with_elderly == false → "rejected"

### Правило 5: Генерация описания (description)
- Объём: 150-300 слов
- Тон: информативный, тёплый, без канцелярита и бюрократизмов
- Структура: 1) Что это за организация и чем занимается, 2) Какие услуги предоставляет для старшего поколения, 3) Как попасть (запись, направление, свободный доступ)
- НЕ КОПИРУЙ текст дословно — перефразируй для целевой аудитории (пожилые люди и их родственники)
- Используй понятную лексику, избегай аббревиатур без расшифровки

### Правило 6: Контакты и адреса
- Телефоны нормализуй в формат: +7XXXXXXXXXX (10 цифр после +7)
- Если указано несколько филиалов — каждый адрес в отдельный объект venues
- Если адрес неполный — добавь в address_raw как есть (Dadata нормализует позже)

### Правило 7: suggested_taxonomy
Используй ТОЛЬКО если обнаружена РЕЛЕВАНТНАЯ для пожилых услуга/специализация, 
которая НЕ МАППИТСЯ ни на один существующий код.
Поле importance_for_elderly ОБЯЗАТЕЛЬНО — объясни, почему это важно для старшего поколения.
"""

    # ═══════════════════════════════════════════
    # БЛОК 3: JSON SCHEMA (статичный)
    # ═══════════════════════════════════════════
    json_schema = OrganizationOutput.model_json_schema()
    schema_block = f"""
## ФОРМАТ ВЫВОДА

Верни ответ в формате json, строго следуя этой JSON Schema:

```json
{json.dumps(json_schema, ensure_ascii=False, indent=2)}
```

ВАЖНО: Верни ТОЛЬКО валидный JSON без дополнительного текста, пояснений или markdown-обёрток.
"""

    # ═══════════════════════════════════════════
    # БЛОК 4: FEW-SHOT EXAMPLES (статичный)
    # ═══════════════════════════════════════════
    examples_block = ORGANIZATION_EXAMPLES  # см. раздел 2.4

    # Сборка финального промпта
    return "\n\n".join([
        dictionaries,      # ~18-22K tokens — кэшируется
        persona_and_rules,  # ~2K tokens — кэшируется 
        schema_block,       # ~1.5K tokens — кэшируется
        examples_block,     # ~3K tokens — кэшируется
    ])


def build_organization_user_message(harvest_input: "HarvestInput") -> str:
    """
    Формирует user message с динамическими данными.
    ВСЕГДА в конце — это суффикс, не кэшируемый DeepSeek.
    
    ВАЖНО: НЕ включать existing_entity_id и is_update — 
    LLM не должна знать об идемпотентности.
    """
    meta_parts = [f"URL источника: {harvest_input.source_url}"]
    if harvest_input.source_kind:
        meta_parts.append(f"Тип источника: {harvest_input.source_kind}")
    if harvest_input.region_hint:
        meta_parts.append(f"Регион: {harvest_input.region_hint}")
    
    meta = "\n".join(meta_parts)
    
    return f"""Проанализируй следующую веб-страницу организации и верни JSON по указанной схеме.

{meta}

--- НАЧАЛО ТЕКСТА СТРАНИЦЫ ---
{harvest_input.raw_text}
--- КОНЕЦ ТЕКСТА СТРАНИЦЫ ---

Верни только JSON."""
```

***

## 2.4. Few-shot примеры (`examples.py`)

```python
"""
Few-shot примеры для system prompt.
По одному примеру на каждый паттерн маршрутизации.
Расположены в статичном блоке system prompt для кэширования.
"""

ORGANIZATION_EXAMPLES = """
## ПРИМЕРЫ КЛАССИФИКАЦИИ

### Пример 1 (Паттерн A — Медицинское учреждение):
ВХОД: "ГБУ «Городская поликлиника №7» ... В нашей поликлинике работает гериатрическое отделение, принимают врач-гериатр и невролог. Для пациентов 60+ доступна программа «Активное долголетие»: бесплатная денситометрия по ОМС, школа пациентов с диабетом. Адрес: г. Калининград, ул. Пролетарская, д.42. Тел: 8(4012)555-123. ИНН: 3906123456"
ВЫХОД:
```json
{
  "source_reference": "example_1",
  "entity_type": "Organization",
  "title": "ГБУ «Городская поликлиника №7»",
  "short_title": "Поликлиника №7",
  "description": "Городская поликлиника №7 в Калининграде — государственное медицинское учреждение с действующим гериатрическим отделением. Для людей старше 60 лет здесь работает программа «Активное долголетие», включающая бесплатную диагностику остеопороза (денситометрию) по полису ОМС и школу для пациентов с сахарным диабетом. Приём ведут врач-гериатр и невролог. Для записи обратитесь в регистратуру по телефону.",
  "inn": "3906123456",
  "ogrn": null,
  "ai_metadata": {
    "works_with_elderly": true,
    "ai_confidence_score": 0.95,
    "ai_explanation": "Организация имеет гериатрическое отделение, программу «Активное долголетие» для 60+, профильных специалистов (гериатр, невролог). ИНН подтверждён.",
    "decision": "accepted"
  },
  "classification": {
    "organization_type_codes": ["140"],
    "ownership_type_code": "154",
    "thematic_category_codes": ["8", "11"],
    "service_codes": ["135", "75"],
    "specialist_profile_codes": ["143", "142"]
  },
  "venues": [{"address_raw": "г. Калининград, ул. Пролетарская, д.42", "address_comment": null}],
  "contacts": {"phones": ["+74012555123"], "emails": [], "website_urls": [], "vk_url": null, "ok_url": null, "telegram_url": null},
  "target_audience": ["elderly"],
  "suggested_taxonomy": []
}
```

### Пример 2 (Паттерн B — Социальная защита):
ВХОД: "КЦСОН Центрального района ... Надомное обслуживание одиноких пожилых: уборка, покупка продуктов, помощь в оплате ЖКХ. Прокат ТСР (коляски, ходунки). Школа ухода для родственников лежачих больных. Горячая линия: 8-800-123-45-67. Адрес: г. Москва, ул. Садовая, 10"
ВЫХОД:
```json
{
  "source_reference": "example_2",
  "entity_type": "Organization",
  "title": "КЦСОН Центрального района",
  "short_title": null,
  "description": "Комплексный центр социального обслуживания населения Центрального района Москвы оказывает помощь одиноким пожилым людям на дому. Социальные работники помогают с уборкой, покупкой продуктов и лекарств, оплатой коммунальных услуг. В центре работает пункт проката технических средств реабилитации — можно взять во временное пользование инвалидную коляску или ходунки. Для родственников, ухаживающих за лежачими больными, организована школа ухода. По всем вопросам звоните на горячую линию.",
  "inn": null,
  "ogrn": null,
  "ai_metadata": {
    "works_with_elderly": true,
    "ai_confidence_score": 0.92,
    "ai_explanation": "КЦСОН по определению работает с пожилыми. Явные маркеры: 'одинокие пожилые', надомное обслуживание, прокат ТСР, школа ухода. ИНН не найден — снижение на 0.03.",
    "decision": "accepted"
  },
  "classification": {
    "organization_type_codes": ["144"],
    "ownership_type_code": "154",
    "thematic_category_codes": ["18", "20", "30"],
    "service_codes": ["108", "109", "106", "114"],
    "specialist_profile_codes": []
  },
  "venues": [{"address_raw": "г. Москва, ул. Садовая, 10", "address_comment": null}],
  "contacts": {"phones": ["+78001234567"], "emails": [], "website_urls": [], "vk_url": null, "ok_url": null, "telegram_url": null},
  "target_audience": ["elderly", "relatives"],
  "suggested_taxonomy": []
}
```

### Пример 3 (Паттерн C — Активное долголетие):
ВХОД: "Центр общения старшего поколения (ЦОСП) при Социальном фонде РФ ... Бесплатные занятия для пенсионеров 55+: скандинавская ходьба (вт, чт 10:00), хор ветеранов (пн, ср 14:00), курсы компьютерной грамотности. VK: vk.com/cosp_kld. Адрес: г. Калининград, пр. Мира, д.5"
ВЫХОД:
```json
{
  "source_reference": "example_3",
  "entity_type": "Organization",
  "title": "Центр общения старшего поколения (ЦОСП) при Социальном фонде РФ",
  "short_title": "ЦОСП Калининград",
  "description": "Центр общения старшего поколения в Калининграде — бесплатная площадка для активного досуга пенсионеров 55+. Здесь проходят занятия скандинавской ходьбой по вторникам и четвергам, репетиции хора ветеранов по понедельникам и средам, а также курсы компьютерной грамотности. Все занятия бесплатны, запись не требуется. Центр работает при региональном отделении Социального фонда России.",
  "inn": null,
  "ogrn": null,
  "ai_metadata": {
    "works_with_elderly": true,
    "ai_confidence_score": 0.97,
    "ai_explanation": "ЦОСП — профильная площадка для пенсионеров. Явный маркер '55+', бесплатные занятия, скандинавская ходьба, хор ветеранов, компьютерные курсы.",
    "decision": "accepted"
  },
  "classification": {
    "organization_type_codes": ["141", "82"],
    "ownership_type_code": "164",
    "thematic_category_codes": ["24", "25", "28", "33"],
    "service_codes": ["93", "70", "84", "75"],
    "specialist_profile_codes": ["96"]
  },
  "venues": [{"address_raw": "г. Калининград, пр. Мира, д.5", "address_comment": null}],
  "contacts": {"phones": [], "emails": [], "website_urls": [], "vk_url": "https://vk.com/cosp_kld", "ok_url": null, "telegram_url": null},
  "target_audience": ["elderly"],
  "suggested_taxonomy": []
}
```
"""


EVENT_EXAMPLES = """
## ПРИМЕРЫ КЛАССИФИКАЦИИ МЕРОПРИЯТИЙ

### Пример 1 (Регулярное офлайн-занятие):
ВХОД: "Скандинавская ходьба для пенсионеров 55+ ... Каждый вторник и четверг в 10:00. Бесплатно. Сбор у входа в парк Южный. Записи нет, приходите! Организатор: ЦОСП Калининград."
ВЫХОД:
```json
{
  "source_reference": "event_example_1",
  "entity_type": "Event",
  "title": "Скандинавская ходьба для пенсионеров 55+",
  "description": "Бесплатные занятия скандинавской ходьбой для людей старше 55 лет в парке Южный. Занятия проходят каждый вторник и четверг в 10:00 утра. Предварительная запись не требуется — просто приходите к входу в парк. Организатор — Центр общения старшего поколения Калининграда.",
  "attendance_mode": "offline",
  "online_url": null,
  "is_free": true,
  "price_description": null,
  "registration_required": false,
  "registration_url": null,
  "organizer_title": "ЦОСП Калининград",
  "organizer_inn": null,
  "schedule": {
    "start_date": null,
    "end_date": null,
    "start_time": "10:00",
    "end_time": null,
    "is_recurring": true,
    "recurrence_description": "каждый вторник и четверг",
    "rrule_suggestion": "FREQ=WEEKLY;BYDAY=TU,TH"
  },
  "ai_metadata": {
    "works_with_elderly": true,
    "ai_confidence_score": 0.98,
    "ai_explanation": "Явный маркер '55+', профильная активность (скандинавская ходьба), бесплатное, при ЦОСП.",
    "decision": "accepted"
  },
  "classification": {
    "event_category_codes": [],
    "thematic_category_codes": ["24"],
    "service_codes": ["93"]
  },
  "venues": [{"address_raw": "Парк Южный, вход", "address_comment": "сбор у входа"}],
  "contacts": {"phones": [], "emails": [], "website_urls": [], "vk_url": null, "ok_url": null, "telegram_url": null},
  "target_audience": ["elderly"],
  "age_restriction": "55+",
  "suggested_taxonomy": []
}
```
"""
```

***

## 2.5. Текст системного промпта: Мероприятия (`event_prompt.py`)

```python
"""
System prompt для классификации и описания мероприятий.
Использует те же справочники, но другие правила экстракции и JSON-схему.
"""
import json
from .dictionaries import build_dictionaries_block
from .schemas import EventOutput
from .examples import EVENT_EXAMPLES


def build_event_system_prompt() -> str:
    dictionaries = build_dictionaries_block()
    
    persona_and_rules = """
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
- Повторяемость: если есть паттерн ("каждый вторник", "по средам и пятницам") — установи is_recurring: true
- rrule_suggestion: попробуй составить RRule если паттерн очевиден. Если не уверен — оставь null
  - Примеры: FREQ=WEEKLY;BYDAY=TU,TH | FREQ=MONTHLY;BYMONTHDAY=1,15 | FREQ=DAILY
- Если дата/время не указаны — оставь null (не выдумывай)

### Правило 3: attendance_mode
- "offline" — физическое присутствие
- "online" — Zoom, Skype, VK-трансляция, запись вебинара
- "mixed" — есть и офлайн-площадка, и онлайн-трансляция

### Правило 4: Стоимость
- Ищи маркеры бесплатности: "бесплатно", "вход свободный", "без оплаты", "по программе Активное долголетие"
- Ищи стоимость: "500 руб.", "по абонементу", "первое занятие бесплатно"
- Если не указано — оставь is_free: null

### Правило 5: Описание (description)
- Объём: 80-200 слов
- Обязательно отразить: для кого, что будет, нужна ли запись, бесплатно ли
- Тон: дружелюбный, понятный для пожилого человека
"""

    json_schema = EventOutput.model_json_schema()
    schema_block = f"""
## ФОРМАТ ВЫВОДА

Верни ответ в формате json, строго следуя этой JSON Schema:

```json
{json.dumps(json_schema, ensure_ascii=False, indent=2)}
```

ВАЖНО: Верни ТОЛЬКО валидный JSON без дополнительного текста, пояснений или markdown-обёрток.
"""

    return "\n\n".join([
        dictionaries,
        persona_and_rules,
        schema_block,
        EVENT_EXAMPLES,
    ])


def build_event_user_message(harvest_input: "HarvestInput") -> str:
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
    
    return f"""Проанализируй следующую страницу с информацией о мероприятии и верни JSON по указанной схеме.

{meta}

--- НАЧАЛО ТЕКСТА СТРАНИЦЫ ---
{harvest_input.raw_text}
--- КОНЕЦ ТЕКСТА СТРАНИЦЫ ---

Верни только JSON."""
```

***

## 2.6. DeepSeek API клиент (`deepseek_client.py`)

```python
"""
Клиент для DeepSeek API с поддержкой:
- JSON mode
- Retry logic с exponential backoff
- Метрики cache hit для мониторинга
- Валидация через Pydantic
"""
import json
import logging
from typing import TypeVar, Type
from openai import OpenAI
from pydantic import BaseModel, ValidationError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class DeepSeekClient:
    """Клиент DeepSeek API, оптимизированный для Harvester v1."""
    
    def __init__(
        self,
        api_key: str,
        model: str = "deepseek-chat",  # deepseek-chat = V3, deepseek-reasoner = R1
        base_url: str = "https://api.deepseek.com",
        max_tokens: int = 4096,
        temperature: float = 0.1,  # Низкая для детерминизма классификации
    ):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        
        # Метрики
        self._total_calls = 0
        self._cache_hits = 0
        self._total_input_tokens = 0
        self._total_output_tokens = 0
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((json.JSONDecodeError, ValidationError)),
        before_sleep=lambda retry_state: logger.warning(
            f"Retry #{retry_state.attempt_number} after error: {retry_state.outcome.exception()}"
        )
    )
    def classify(
        self,
        system_prompt: str,
        user_message: str,
        output_model: Type[T],
    ) -> T:
        """
        Отправляет запрос к DeepSeek и парсит ответ в Pydantic-модель.
        
        Args:
            system_prompt: Полный system prompt (справочники + правила + schema + examples)
            user_message: Динамический user message с raw_text
            output_model: Pydantic-модель для десериализации ответа
            
        Returns:
            Провалидированный экземпляр output_model
            
        Raises:
            json.JSONDecodeError: если ответ не парсится как JSON (retry)
            ValidationError: если JSON не проходит Pydantic-валидацию (retry)
        """
        self._total_calls += 1
        
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            response_format={"type": "json_object"},
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            stream=False,
        )
        
        # Метрики кэширования
        usage = response.usage
        if usage:
            self._total_input_tokens += usage.prompt_tokens
            self._total_output_tokens += usage.completion_tokens
            
            # DeepSeek возвращает prompt_cache_hit_tokens в usage
            cache_hit_tokens = getattr(usage, "prompt_cache_hit_tokens", 0)
            if cache_hit_tokens > 0:
                self._cache_hits += 1
                logger.info(
                    f"Cache HIT: {cache_hit_tokens}/{usage.prompt_tokens} tokens cached "
                    f"({cache_hit_tokens/usage.prompt_tokens*100:.1f}%)"
                )
        
        # Парсинг JSON
        raw_content = response.choices.message.content.strip()
        
        # Очистка от возможных markdown-обёрток
        if raw_content.startswith("```"):
            raw_content = raw_content.split("\n", 1)  # убрать ```json
            raw_content = raw_content.rsplit("```", 1)  # убрать закрывающий ```
        
        parsed = json.loads(raw_content)
        
        # Валидация через Pydantic
        result = output_model.model_validate(parsed)
        
        logger.info(
            f"Classified: {result.title if hasattr(result, 'title') else 'N/A'} | "
            f"Score: {result.ai_metadata.ai_confidence_score} | "
            f"Decision: {result.ai_metadata.decision}"
        )
        
        return result
    
    def get_metrics(self) -> dict:
        """Возвращает метрики для мониторинга."""
        return {
            "total_calls": self._total_calls,
            "cache_hit_rate": self._cache_hits / max(self._total_calls, 1),
            "total_input_tokens": self._total_input_tokens,
            "total_output_tokens": self._total_output_tokens,
            "estimated_cost_usd": (
                self._total_input_tokens / 1_000_000 * 0.014 +  # optimistic: all cached
                self._total_output_tokens / 1_000_000 * 0.28
            ),
        }
```

***

## 2.7. Оркестратор обработки (`organization_processor.py`)

```python
"""
Оркестратор обработки организаций через AI-пайплайн.
Связывает HarvestInput → System Prompt → DeepSeek API → OrganizationOutput.
"""
import logging
from ..prompts.organization_prompt import (
    build_organization_system_prompt,
    build_organization_user_message,
)
from ..prompts.schemas import HarvestInput, OrganizationOutput, EntityType
from ..processors.deepseek_client import DeepSeekClient

logger = logging.getLogger(__name__)


class OrganizationProcessor:
    """Обрабатывает сырые данные об организации через LLM."""
    
    def __init__(self, deepseek_client: DeepSeekClient):
        self.client = deepseek_client
        # System prompt собирается ОДИН РАЗ и переиспользуется для всех вызовов.
        # Это критично для prefix caching!
        self._system_prompt = build_organization_system_prompt()
        logger.info(
            f"Organization system prompt built: ~{len(self._system_prompt)} chars"
        )
    
    def process(self, harvest_input: HarvestInput) -> OrganizationOutput:
        """
        Обработка одной организации через LLM.
        Возвращает OrganizationOutput с классификацией и описанием.
        Поля existing_entity_id / is_update устанавливаются отдельно в process_and_sync.
        """
        assert harvest_input.entity_type == EntityType.ORGANIZATION
        
        user_message = build_organization_user_message(harvest_input)
        
        result = self.client.classify(
            system_prompt=self._system_prompt,
            user_message=user_message,
            output_model=OrganizationOutput,
        )
        
        # Post-processing: установить source_reference
        result.source_reference = harvest_input.source_item_id
        
        # Валидация: коды должны существовать в справочниках
        self._validate_codes(result)
        
        return result
    
    def _validate_codes(self, result: OrganizationOutput):
        """
        Post-hoc валидация: проверяет, что все коды существуют в справочниках.
        Логирует warning при невалидных кодах (не блокирует).
        """
        from ..prompts.dictionaries import load_all_dictionaries
        dicts = load_all_dictionaries()
        
        valid_codes = {
            "organization_types": {item["code"] for item in dicts["organization_types"]},
            "ownership_types": {item["code"] for item in dicts["ownership_types"]},
            "thematic_categories": {item["code"] for item in dicts["thematic_categories"]},
            "services": {item["code"] for item in dicts["services"]},
            "specialist_profiles": {item["code"] for item in dicts["specialist_profiles"]},
        }
        
        cls = result.classification
        
        for code in cls.organization_type_codes:
            if code not in valid_codes["organization_types"]:
                logger.warning(f"Invalid organization_type code: {code} in {result.title}")
        
        if cls.ownership_type_code and cls.ownership_type_code not in valid_codes["ownership_types"]:
            logger.warning(f"Invalid ownership_type code: {cls.ownership_type_code} in {result.title}")
        
        for code in cls.thematic_category_codes:
            if code not in valid_codes["thematic_categories"]:
                logger.warning(f"Invalid thematic_category code: {code} in {result.title}")
        
        for code in cls.service_codes:
            if code not in valid_codes["services"]:
                logger.warning(f"Invalid service code: {code} in {result.title}")
        
        for code in cls.specialist_profile_codes:
            if code not in valid_codes["specialist_profiles"]:
                logger.warning(f"Invalid specialist_profile code: {code} in {result.title}")
    
    def process_and_sync(self, harvest_input: HarvestInput) -> dict:
        """
        Полный цикл: LLM → Pydantic → решение CREATE / UPDATE / OUTDATED.
        Это точка входа для идемпотентного пайплайна (см. раздел 2.12).
        """
        # 1. Вызов LLM
        org = self.process(harvest_input)
        
        # 2. Привязка идемпотентности (LLM про это не знает)
        org.existing_entity_id = harvest_input.existing_entity_id
        org.is_update = harvest_input.existing_entity_id is not None
        
        # 3. Decision routing
        decision = org.ai_metadata.decision
        
        if decision == "rejected":
            if org.is_update:
                return self._mark_as_outdated(org.existing_entity_id, org)
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
        """POST /api/internal/import/organizer — создание новой записи."""
        payload = to_core_import_payload(result)
        payload["action"] = "create"
        # TODO: реализовать HTTP-вызов к Navigator Core API
        return {"action": "created", "payload": payload}
    
    def _update_organizer(self, result: OrganizationOutput) -> dict:
        """PATCH /api/internal/organizers/{id} — обновление существующей записи."""
        payload = to_core_import_payload(result)
        payload["action"] = "update"
        payload["existing_entity_id"] = result.existing_entity_id
        return {"action": "updated", "payload": payload}
    
    def _update_organizer_with_review(self, result: OrganizationOutput) -> dict:
        """UPDATE + флаг модерации."""
        payload = to_core_import_payload(result)
        payload["action"] = "update"
        payload["existing_entity_id"] = result.existing_entity_id
        payload["requires_review"] = True
        return {"action": "updated_needs_review", "payload": payload}
    
    def _create_draft(self, result: OrganizationOutput) -> dict:
        """CREATE в статусе pending_review."""
        payload = to_core_import_payload(result)
        payload["action"] = "create_draft"
        return {"action": "created_draft", "payload": payload}
    
    def _mark_as_outdated(self, entity_id: str, result: OrganizationOutput) -> dict:
        """
        Пометить существующую запись как устаревшую:
        при повторном обходе LLM решил, что организация больше не релевантна.
        """
        return {
            "action": "mark_outdated",
            "existing_entity_id": entity_id,
            "ai_explanation": result.ai_metadata.ai_explanation,
        }
    
    def process_batch(
        self,
        items: list[HarvestInput],
        on_success: callable = None,
        on_error: callable = None,
    ) -> list[dict]:
        """
        Последовательная обработка пакета организаций.
        System prompt при этом ОДИН — максимальный cache hit.
        """
        results = []
        for i, item in enumerate(items):
            try:
                result = self.process_and_sync(item)
                results.append(result)
                if on_success:
                    on_success(i, result)
            except Exception as e:
                logger.error(f"Failed to process {item.source_item_id}: {e}")
                if on_error:
                    on_error(i, item, e)
        
        metrics = self.client.get_metrics()
        logger.info(
            f"Batch complete: {len(results)}/{len(items)} successful. "
            f"Cache hit rate: {metrics['cache_hit_rate']:.1%}. "
            f"Est. cost: ${metrics['estimated_cost_usd']:.4f}"
        )
        
        return results
```

***

## 2.8. Контракт с Navigator Core API

Функция конвертации `OrganizationOutput` в формат `POST /api/internal/import/organizer`:

```python
def to_core_import_payload(org: OrganizationOutput) -> dict:
    """Конвертация OrganizationOutput в формат API Navigator Core."""
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
        "suggested_taxonomy": [
            s.model_dump() for s in org.suggested_taxonomy
        ],
    }
```

***

## 2.9. Оценка стоимости и производительности

| Компонент | Токены (оценка) |
|-----------|----------------|
| Справочники (5 файлов) | ~18,000–22,000 |
| Персона + правила | ~2,000 |
| JSON Schema | ~1,500 |
| Few-shot examples | ~3,000 |
| **Итого system prompt** | **~25,000–28,000** |
| User message (avg) | ~3,500 |
| Output (avg) | ~1,200 |

| Метрика | Значение |
|---------|----------|
| Стоимость 10,000 организаций (cache hit) | ~$7.50 |
| Стоимость 10,000 организаций (cache miss) | ~$48.00 |
| Целевой cache hit rate | >90% |
| Время обработки 1 элемента | ~3–8 сек |

***

## 2.10. Стратегия тестирования (`tests/`)

```python
# tests/test_schemas.py

import pytest
from navigator_harvester.prompts.schemas import (
    OrganizationOutput, EventOutput, AIConfidenceMetadata
)


def test_organization_output_valid():
    """Проверяет, что валидный JSON парсится без ошибок."""
    data = {
        "source_reference": "test_1",
        "entity_type": "Organization",
        "title": "Тестовая организация",
        "description": "Описание тестовой организации для проверки схемы.",
        "ai_metadata": {
            "works_with_elderly": True,
            "ai_confidence_score": 0.95,
            "ai_explanation": "Тестовое обоснование.",
            "decision": "accepted"
        },
        "classification": {
            "organization_type_codes": ["141"],
            "ownership_type_code": "154",
            "thematic_category_codes": ["24"],
            "service_codes": ["93"],
            "specialist_profile_codes": []
        },
        "venues": [],
        "contacts": {"phones": [], "emails": [], "website_urls": []},
        "target_audience": ["elderly"],
        "suggested_taxonomy": []
    }
    result = OrganizationOutput.model_validate(data)
    assert result.ai_metadata.decision == "accepted"
    assert result.classification.organization_type_codes == ["141"]


def test_confidence_score_bounds():
    """ai_confidence_score должен быть в диапазоне [0, 1]."""
    with pytest.raises(Exception):
        AIConfidenceMetadata(
            works_with_elderly=True,
            ai_confidence_score=1.5,  # НЕВАЛИДНО
            ai_explanation="test",
            decision="accepted"
        )


def test_invalid_decision():
    """decision должен быть одним из accepted/rejected/needs_review."""
    with pytest.raises(Exception):
        AIConfidenceMetadata(
            works_with_elderly=True,
            ai_confidence_score=0.9,
            ai_explanation="test",
            decision="maybe"  # НЕВАЛИДНО
        )


# tests/test_prompts.py

def test_dictionaries_block_is_deterministic():
    """Блок справочников должен быть идентичен при повторных вызовах (для кэширования)."""
    from navigator_harvester.prompts.dictionaries import build_dictionaries_block
    block1 = build_dictionaries_block()
    block2 = build_dictionaries_block()
    assert block1 == block2, "Dictionary block must be deterministic for caching"


def test_system_prompt_starts_with_dictionaries():
    """System prompt ДОЛЖЕН начинаться со справочников (prefix caching)."""
    from navigator_harvester.prompts.organization_prompt import build_organization_system_prompt
    prompt = build_organization_system_prompt()
    assert prompt.startswith("=" * 60), "Prompt must start with dictionaries block"


def test_system_prompt_contains_json_keyword():
    """Промпт ОБЯЗАН содержать слово 'json' для активации JSON mode DeepSeek."""
    from navigator_harvester.prompts.organization_prompt import build_organization_system_prompt
    prompt = build_organization_system_prompt()
    assert "json" in prompt.lower(), "Prompt must contain 'json' keyword for DeepSeek JSON mode"
```

***

## 2.11. Критически важные инструкции для реализации

1. **НЕ МЕНЯТЬ порядок блоков в system prompt** — справочники ВСЕГДА первые (prefix caching).
2. **НЕ ДОБАВЛЯТЬ динамические переменные** (дату, URL, session_id) в system prompt — только в user message.
3. **`build_dictionaries_block()` и `build_organization_system_prompt()` вызываются ОДИН РАЗ** при инициализации процессора, затем переиспользуются. Никогда не пересобирать промпт на каждый вызов API.
4. **Pydantic-модели** являются контрактом между AI-пайплайном и Laravel Core. Изменения в схемах должны синхронизироваться с миграциями базы данных.
5. **`temperature=0.1`** — для классификации нужен детерминизм. Не повышать без веской причины.
6. **Все коды в справочниках — строки** (не числа). `"141"`, не `141`. Pydantic-модели должны использовать `list[str]`, не `list[int]`.
7. **Retry logic** — при `JSONDecodeError` или `ValidationError` делается до 3 попыток с exponential backoff. Если все 3 провалились — элемент логируется и пропускается.
8. **Event processing** использует тот же `build_dictionaries_block()` — справочники общие, только правила и JSON-схема отличаются.
9. **Поля `existing_entity_id` и `is_update`** НЕ передаются в LLM — они устанавливаются в post-processing на стороне Python (см. раздел 2.12).

***

## 2.12. Идемпотентность и повторный обход существующей базы

### 2.12.1. Проблема

При повторных обходах одного и того же источника (например, ежемесячный перекраул сайтов организаций) необходимо решить: создавать новую запись или обновлять уже существующую. Без механизма идемпотентности каждый обход будет плодить дубликаты.

### 2.12.2. Уникальный ключ: `(source_id, source_item_id)`

Идентификация сущности при повторных обходах строится на **двух уровнях**:

1. **Технический ключ источника**: пара `(source_id, source_item_id)`.
   - `source_id` — UUID записи в таблице `sources` (один конкретный источник данных: реестр, сайт, VK-группа).
   - `source_item_id` — стабильный идентификатор внутри этого источника (URL slug, entry ID реестра, API-идентификатор). Формируется Harvester'ом при первом обнаружении.
   - Пара `(source_id, source_item_id)` должна быть уникальным составным индексом в Navigator Core для таблиц organizers и events.

2. **Бизнес-ключ организации** (вторичный, для кросс-источниковой дедупликации): ИНН / ОГРН + название. Используется, когда одна и та же организация присутствует в разных источниках (реестр СФР + собственный сайт).

### 2.12.3. Последовательность обработки

```
Harvester получает raw_text из source
        │
        ▼
Формирует source_item_id из URL/entry_id
        │
        ▼
Запрос к Core API: GET /api/internal/organizers?source_id=X&source_item_id=Y
        │
        ├── Найдена запись → existing_entity_id = UUID найденной записи
        │
        └── Не найдена → existing_entity_id = null
        │
        ▼
Формируется HarvestInput (с existing_entity_id)
        │
        ▼
Вызов LLM (LLM НЕ знает про existing_entity_id)
        │
        ▼
OrganizationOutput получена, is_update вычислено из existing_entity_id
        │
        ▼
Decision routing (см. таблицу ниже)
```

### 2.12.4. Таблица маршрутизации решений

| Сценарий | `existing_entity_id` | `ai_metadata.decision` | Действие Harvester | HTTP метод Core API |
|----------|----------------------|------------------------|--------------------|---------------------|
| Новая организация, релевантна | `null` | `accepted` | CREATE organizer | `POST /import/organizer` |
| Новая организация, сомнительна | `null` | `needs_review` | CREATE draft (status=pending_review) | `POST /import/organizer` |
| Новая организация, нерелевантна | `null` | `rejected` | Пропустить, не создавать | — |
| Повторный обход, релевантна | UUID | `accepted` | UPDATE organizer | `PATCH /organizers/{id}` |
| Повторный обход, сомнительна | UUID | `needs_review` | UPDATE + флаг модерации | `PATCH /organizers/{id}` |
| Повторный обход, нерелевантна | UUID | `rejected` | Пометить status=outdated | `PATCH /organizers/{id}` |

### 2.12.5. Lookup существующей записи

```python
def find_existing_entity(
    source_id: str,
    source_item_id: str,
    entity_type: EntityType,
    core_api_url: str,
    api_token: str,
) -> Optional[str]:
    """
    Поиск существующей записи в Navigator Core по составному ключу.
    Возвращает UUID или None.
    
    Вызывается Harvester'ом ДО обращения к LLM.
    """
    endpoint = "organizers" if entity_type == EntityType.ORGANIZATION else "events"
    
    response = requests.get(
        f"{core_api_url}/api/internal/{endpoint}",
        params={
            "source_id": source_id,
            "source_item_id": source_item_id,
        },
        headers={"Authorization": f"Bearer {api_token}"},
        timeout=10,
    )
    
    if response.status_code == 200:
        data = response.json().get("data", [])
        if data:
            return data["id"]
    
    return None
```

### 2.12.6. Кросс-источниковая дедупликация (дополнительный уровень)

Если одна организация присутствует в нескольких источниках (реестр СФР + собственный сайт + VK-группа), каждый источник создаст свою запись (разные `source_id`). Для их объединения используется бизнес-ключ:

```python
def find_by_business_key(
    inn: Optional[str],
    ogrn: Optional[str],
    title: str,
    core_api_url: str,
    api_token: str,
) -> Optional[str]:
    """
    Поиск по ИНН/ОГРН (точное совпадение) или по нечёткому сравнению названий.
    Вызывается ПОСЛЕ получения OrganizationOutput от LLM, если inn/ogrn извлечены.
    """
    params = {}
    if inn:
        params["inn"] = inn
    elif ogrn:
        params["ogrn"] = ogrn
    else:
        return None  # без ИНН/ОГРН кросс-дедупликация невозможна
    
    response = requests.get(
        f"{core_api_url}/api/internal/organizers/lookup",
        params=params,
        headers={"Authorization": f"Bearer {api_token}"},
        timeout=10,
    )
    
    if response.status_code == 200:
        data = response.json().get("data", [])
        if data:
            return data["id"]
    
    return None
```

Стратегии слияния при обнаружении кросс-дублей:

- **enrich** — дополнить существующую запись данными из нового источника (добавить услуги, контакты, адреса).
- **replace** — заменить описание и классификацию, если новый источник более авторитетный.
- **keep_both** — оставить обе записи (разные филиалы одной организации).

Выбор стратегии — задача Navigator Core API, а не Harvester'а. Harvester передаёт в payload поле `merge_candidate_id`, и Core принимает решение.

***

*Спецификация подготовлена на основе архитектурной доменной модели Navigator Core, документа `harvester_v1_prompt.md` и актуальных справочников платформы.*