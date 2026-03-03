"""Tests for FPG project filter pipeline."""

import os

import pytest

from aggregators.fpg.models import FPGOrganization, FPGProject
from aggregators.fpg.project_filter import (
    ELDERLY_PATTERN,
    deduplicate_by_org,
    filter_by_direction,
    filter_by_status,
    filter_elderly_relevant,
    run_filter_pipeline,
)
from aggregators.fpg.xlsx_parser import parse_xlsx

FIXTURE_PATH = os.path.join(
    os.path.dirname(__file__), "fixtures", "fpg_sample.xlsx"
)


@pytest.fixture
def all_projects() -> list[FPGProject]:
    return parse_xlsx(FIXTURE_PATH)


class TestDirectionFilter:
    def test_keeps_relevant_directions(self, all_projects: list[FPGProject]):
        filtered = filter_by_direction(all_projects)
        # Excludes "охрана окружающей среды" (row index 3)
        directions = {p.grant_direction for p in filtered}
        assert "охрана окружающей среды и защита животных" not in directions

    def test_counts_correct(self, all_projects: list[FPGProject]):
        filtered = filter_by_direction(all_projects)
        assert len(filtered) == 7  # 8 total - 1 ecology = 7


class TestStatusFilter:
    def test_excludes_withdrawn(self, all_projects: list[FPGProject]):
        filtered = filter_by_status(all_projects)
        for p in filtered:
            assert "отозван" not in p.status.lower()

    def test_excludes_bad_evaluation(self, all_projects: list[FPGProject]):
        filtered = filter_by_status(all_projects)
        for p in filtered:
            if p.evaluation:
                assert p.evaluation != "проект реализован неудовлетворительно"

    def test_counts_correct(self, all_projects: list[FPGProject]):
        filtered = filter_by_status(all_projects)
        # 8 total - 1 withdrawn - 1 bad eval = 6
        assert len(filtered) == 6


class TestElderlyKeywords:
    def test_matches_elderly_keywords(self):
        test_cases = [
            ("Активное долголетие для пожилых", True),
            ("Здоровое долголетие для пенсионеров", True),
            ("Серебряные волонтеры: помощь пожилым", True),
            ("Компьютерная грамотность для людей старшего возраста", True),
            ("Уход за престарелыми", True),
            ("Поддержка ветеранов труда", True),
            ("Геронтологический центр", True),
            ("Детский фитнес-марафон", False),
            ("Чистые берега Волги", False),
            ("Развитие молодежного спорта", False),
        ]
        for text, expected in test_cases:
            result = bool(ELDERLY_PATTERN.search(text))
            assert result == expected, f"'{text}': expected {expected}, got {result}"

    def test_filter_from_sample(self, all_projects: list[FPGProject]):
        direction_filtered = filter_by_direction(all_projects)
        status_filtered = filter_by_status(direction_filtered)
        elderly = filter_elderly_relevant(status_filtered)
        # Expected: rows 0, 1, 2, 7 have elderly keywords; 5 (withdrawn) and 6 (bad eval) excluded
        assert len(elderly) == 4


class TestDedup:
    def test_groups_by_inn(self, all_projects: list[FPGProject]):
        direction_filtered = filter_by_direction(all_projects)
        elderly = filter_elderly_relevant(direction_filtered)
        orgs = deduplicate_by_org(elderly)

        inns = [o.inn for o in orgs]
        # rows 0 and 2 share INN 7701234567
        assert "7701234567" in inns

        org_with_two = next(o for o in orgs if o.inn == "7701234567")
        assert org_with_two.project_count == 2
        assert org_with_two.has_winning_project is True

    def test_sorted_by_project_count(self, all_projects: list[FPGProject]):
        direction_filtered = filter_by_direction(all_projects)
        elderly = filter_elderly_relevant(direction_filtered)
        orgs = deduplicate_by_org(elderly)
        counts = [o.project_count for o in orgs]
        assert counts == sorted(counts, reverse=True)


class TestFullPipeline:
    def test_end_to_end(self, all_projects: list[FPGProject]):
        orgs, stats = run_filter_pipeline(all_projects)

        assert stats.total_input == 8
        assert stats.after_direction == 7
        assert stats.after_status > 0
        assert stats.after_elderly > 0
        assert stats.unique_organizations == len(orgs)
        assert all(isinstance(o, FPGOrganization) for o in orgs)

    def test_summary_is_string(self, all_projects: list[FPGProject]):
        _, stats = run_filter_pipeline(all_projects)
        summary = stats.summary()
        assert isinstance(summary, str)
        assert "Direction breakdown" in summary
