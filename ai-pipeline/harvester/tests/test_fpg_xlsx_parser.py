"""Tests for FPG XLSX parser."""

import os
from datetime import date

import pytest

from aggregators.fpg.models import FPGProject
from aggregators.fpg.xlsx_parser import parse_xlsx

FIXTURE_PATH = os.path.join(
    os.path.dirname(__file__), "fixtures", "fpg_sample.xlsx"
)


@pytest.fixture
def sample_projects() -> list[FPGProject]:
    return parse_xlsx(FIXTURE_PATH)


class TestParseXlsx:
    def test_parses_all_rows(self, sample_projects: list[FPGProject]):
        assert len(sample_projects) == 8

    def test_first_row_fields(self, sample_projects: list[FPGProject]):
        p = sample_projects[0]
        assert p.application_number == "24-1-001234"
        assert p.contest == "Первый конкурс 2024 г."
        assert p.organization_name == 'АНО "ЗАБОТА О СТАРШЕМ ПОКОЛЕНИИ"'
        assert p.ogrn == "1027700123456"
        assert p.inn == "7701234567"
        assert p.region == "Москва"
        assert p.grant_direction == "социальное обслуживание, социальная поддержка и защита граждан"
        assert p.budget_requested == 5_000_000
        assert p.budget_total == 6_000_000
        assert p.start_date == date(2024, 3, 1)
        assert p.end_date == date(2025, 3, 1)
        assert p.status == "победитель конкурса"
        assert p.grant_decision_date == date(2024, 2, 1)
        assert p.grant_amount == 4_500_000
        assert p.evaluation == "проект реализован успешно"
        assert p.violations is None

    def test_non_winner_fields(self, sample_projects: list[FPGProject]):
        p = sample_projects[1]
        assert p.status == "проект не получил поддержки"
        assert p.grant_decision_date is None
        assert p.grant_amount is None
        assert p.evaluation is None

    def test_is_winner_property(self, sample_projects: list[FPGProject]):
        assert sample_projects[0].is_winner is True
        assert sample_projects[1].is_winner is False
        assert sample_projects[3].is_winner is False

    def test_source_reference(self, sample_projects: list[FPGProject]):
        assert sample_projects[0].source_reference == "fpg_24-1-001234"

    def test_inn_ogrn_coerced_to_string(self, sample_projects: list[FPGProject]):
        for p in sample_projects:
            assert isinstance(p.inn, str)
            assert isinstance(p.ogrn, str)

    def test_limit_parameter(self):
        projects = parse_xlsx(FIXTURE_PATH, limit=3)
        assert len(projects) == 3

    def test_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            parse_xlsx("/nonexistent/path.xlsx")
