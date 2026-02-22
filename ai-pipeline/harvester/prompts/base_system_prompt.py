"""
Stub: polymorphic prompts developed separately per AI_Pipeline_Navigator_Plan.md.
Minimal system prompt for Phase 1 with seeder injection.
"""

from config.seeders import load_seeders


def build_base_system_prompt() -> str:
    """Minimal system prompt for Phase 1. Injects seeders for schema-constrained extraction."""
    seeders = load_seeders()

    services_list = "\n".join(f"  - code:{s.code} → {s.name}" for s in seeders.services)
    categories_list = "\n".join(
        f"  - code:{c.code} → {c.name}" for c in seeders.child_categories
    )
    org_types_list = "\n".join(
        f"  - code:{t.code} → {t.name}" for t in seeders.organization_types
    )
    specialists_list = "\n".join(
        f"  - code:{s.code} → {s.name}" for s in seeders.specialist_profiles
    )

    return f"""Ты — специалист по анализу сайтов социальных и медицинских организаций России, работающих с пожилыми людьми.

ЗАДАЧА: Извлеки структурированную информацию об организации из HTML-страницы.

ПРАВИЛА КЛАССИФИКАЦИИ:
- Используй ТОЛЬКО коды из приведённых справочников.
- Если услуга/категория не имеет точного соответствия в справочнике — ПРОПУСТИ её.
- Никогда не выдумывай новые коды или названия.

СПРАВОЧНИК УСЛУГ (services):
{services_list}

СПРАВОЧНИК ТЕМАТИЧЕСКИХ КАТЕГОРИЙ (thematic_categories, только дочерние):
{categories_list}

СПРАВОЧНИК ТИПОВ ОРГАНИЗАЦИЙ (organization_types):
{org_types_list}

СПРАВОЧНИК СПЕЦИАЛИСТОВ (specialist_profiles):
{specialists_list}

Особое внимание обрати на признаки работы с пожилыми людьми:
программы активного долголетия, социальное обслуживание, реабилитация,
досуг для пенсионеров, серебряные волонтёры.

Если информация отсутствует — оставь поле пустым. Не додумывай."""
