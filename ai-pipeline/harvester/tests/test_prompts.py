"""
Тесты system prompt: детерминизм, структура, совместимость с DeepSeek JSON mode.
"""

from prompts.dictionaries import build_dictionaries_block, load_all_dictionaries
from prompts.event_prompt import build_event_system_prompt
from prompts.organization_prompt import build_organization_system_prompt


class TestDictionariesBlock:
    def test_deterministic(self):
        """Блок справочников должен быть идентичен при повторных вызовах (для кэширования)."""
        block1 = build_dictionaries_block()
        block2 = build_dictionaries_block()
        assert block1 == block2, "Dictionary block must be deterministic for caching"

    def test_starts_with_separator(self):
        block = build_dictionaries_block()
        assert block.startswith("=" * 60)

    def test_ends_with_separator(self):
        block = build_dictionaries_block()
        assert block.strip().endswith("=" * 60)

    def test_contains_all_dictionaries(self):
        block = build_dictionaries_block()
        for name in [
            "THEMATIC_CATEGORIES",
            "ORGANIZATION_TYPES",
            "SERVICES",
            "SPECIALIST_PROFILES",
            "OWNERSHIP_TYPES",
        ]:
            assert name in block, f"Missing dictionary: {name}"

    def test_only_active_items_loaded(self):
        dicts = load_all_dictionaries()
        for name, items in dicts.items():
            for item in items:
                assert item.get("is_active", True), (
                    f"Inactive item loaded in {name}: {item.get('code')}"
                )

    def test_thematic_categories_have_hierarchy(self):
        dicts = load_all_dictionaries()
        cats = dicts["thematic_categories"]
        parents = [c for c in cats if c.get("parent_code") is None]
        children = [c for c in cats if c.get("parent_code") is not None]
        assert len(parents) >= 3, "Expected at least 3 parent categories"
        assert len(children) >= 15, "Expected at least 15 child categories"


class TestOrganizationSystemPrompt:
    def test_starts_with_dictionaries(self):
        """System prompt ДОЛЖЕН начинаться со справочников (prefix caching)."""
        prompt = build_organization_system_prompt()
        assert prompt.startswith("=" * 60), "Prompt must start with dictionaries block"

    def test_contains_json_keyword(self):
        """Промпт ОБЯЗАН содержать слово 'json' для активации JSON mode DeepSeek."""
        prompt = build_organization_system_prompt()
        assert "json" in prompt.lower(), "Prompt must contain 'json' keyword"

    def test_contains_routing_patterns(self):
        prompt = build_organization_system_prompt()
        assert "ПАТТЕРН A" in prompt
        assert "ПАТТЕРН B" in prompt
        assert "ПАТТЕРН C" in prompt

    def test_contains_decision_rules(self):
        prompt = build_organization_system_prompt()
        assert "accepted" in prompt
        assert "rejected" in prompt
        assert "needs_review" in prompt

    def test_contains_few_shot_examples(self):
        prompt = build_organization_system_prompt()
        assert "ПРИМЕРЫ КЛАССИФИКАЦИИ" in prompt

    def test_no_dynamic_variables(self):
        """System prompt не должен содержать динамических переменных."""
        prompt = build_organization_system_prompt()
        assert "{" not in prompt or "```json" in prompt, (
            "System prompt should not contain unresolved template variables"
        )


class TestEventSystemPrompt:
    def test_starts_with_dictionaries(self):
        prompt = build_event_system_prompt()
        assert prompt.startswith("=" * 60)

    def test_contains_json_keyword(self):
        prompt = build_event_system_prompt()
        assert "json" in prompt.lower()

    def test_contains_schedule_rules(self):
        prompt = build_event_system_prompt()
        assert "rrule" in prompt.lower() or "RRule" in prompt

    def test_contains_attendance_mode_rules(self):
        prompt = build_event_system_prompt()
        assert "offline" in prompt
        assert "online" in prompt
        assert "mixed" in prompt

    def test_shares_dictionaries_with_organization(self):
        """Оба промпта используют одинаковый блок справочников (prefix sharing)."""
        org_prompt = build_organization_system_prompt()
        event_prompt = build_event_system_prompt()
        dict_block = build_dictionaries_block()
        assert org_prompt.startswith(dict_block)
        assert event_prompt.startswith(dict_block)
