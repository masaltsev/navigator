"""
Загрузка и форматирование справочников для инжекции в system prompt.

КРИТИЧНО для DeepSeek prefix caching:
  - Порядок загрузки ФИКСИРОВАН (DICTIONARY_LOAD_ORDER)
  - Результат ДЕТЕРМИНИРОВАН (lru_cache)
  - Блок справочников располагается ПЕРВЫМ в system prompt
"""

import json
from functools import lru_cache
from pathlib import Path

SEEDERS_DIR = Path(__file__).resolve().parent.parent / "seeders_data"

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
    result: dict[str, list[dict]] = {}
    for name in DICTIONARY_LOAD_ORDER:
        file_path = SEEDERS_DIR / f"{name}.json"
        with open(file_path, encoding="utf-8") as f:
            raw = json.load(f)
        result[name] = [item for item in raw if item.get("is_active", True)]
    return result


def format_dictionary_for_prompt(name: str, items: list[dict]) -> str:
    """
    Форматирует справочник в компактный текстовый блок для system prompt.

    Оптимизации:
      1. Минимизация токенов (убираем id, is_active — модели нужен только code)
      2. Ключевые слова inline для семантического выравнивания
      3. Для thematic_categories — иерархия parent→children
    """
    lines = [f"### СПРАВОЧНИК: {name.upper()}"]

    if name == "thematic_categories":
        parents = {
            item["code"]: item
            for item in items
            if item.get("parent_code") is None
        }
        children = [item for item in items if item.get("parent_code") is not None]

        for p_code in sorted(parents, key=lambda c: int(c)):
            parent = parents[p_code]
            kw = ", ".join(parent.get("keywords", []))
            lines.append(f"\n#### {parent['name']} (родительский код: {p_code})")
            lines.append(f"  Описание: {parent.get('description', '')}")
            lines.append(f"  Ключевые слова: {kw}")

            for child in sorted(children, key=lambda x: int(x["code"])):
                if child.get("parent_code") == p_code:
                    ckw = ", ".join(child.get("keywords", []))
                    lines.append(
                        f"  - код \"{child['code']}\": {child['name']} "
                        f"| {child.get('description', '')} "
                        f"| keywords: [{ckw}]"
                    )
    else:
        for item in sorted(items, key=lambda x: int(x["code"])):
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
    blocks: list[str] = []

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
