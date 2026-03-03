"""Tests for SONKO XLSX parser."""

import os

import pytest

from aggregators.sonko.models import SONKOEntry
from aggregators.sonko.xlsx_parser import parse_xlsx

FIXTURE_PATH = os.path.join(
    os.path.dirname(__file__), "fixtures", "sonko_sample.xlsx"
)


@pytest.fixture
def sample_entries() -> list[SONKOEntry]:
    return parse_xlsx(FIXTURE_PATH)


class TestParseXlsx:
    def test_parses_all_data_rows(self, sample_entries: list[SONKOEntry]):
        assert len(sample_entries) == 8

    def test_skips_empty_rows(self, sample_entries: list[SONKOEntry]):
        for entry in sample_entries:
            assert len(entry.inn) >= 5

    def test_first_row_fields(self, sample_entries: list[SONKOEntry]):
        e = sample_entries[0]
        assert e.inn == "7701234567"
        assert "ДОБРО" in e.full_name
        assert e.short_name == 'АНО "ДОБРО"'
        assert e.ogrn == "1027700123456"
        assert e.okved == "88.10"
        assert e.sonko_status == "Получатель субсидий или грантов"
        assert e.address != ""

    def test_inn_ogrn_stripped(self, sample_entries: list[SONKOEntry]):
        for e in sample_entries:
            assert not e.inn.endswith(" ")
            assert not e.ogrn.endswith(" ")

    def test_okved_prefix(self, sample_entries: list[SONKOEntry]):
        assert sample_entries[0].okved_prefix == "88"
        assert sample_entries[2].okved_prefix == "87"

    def test_source_reference(self, sample_entries: list[SONKOEntry]):
        assert sample_entries[0].source_reference == "sonko_7701234567"

    def test_limit_parameter(self):
        entries = parse_xlsx(FIXTURE_PATH, limit=3)
        assert len(entries) == 3

    def test_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            parse_xlsx("/nonexistent/path.xlsx")
