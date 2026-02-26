"""Tests for SONKO organization filter pipeline."""

import os

import pytest

from aggregators.sonko.models import SONKOEntry, SONKOOrganization
from aggregators.sonko.org_filter import (
    ELDERLY_PATTERN,
    deduplicate_by_inn,
    filter_by_name_keywords,
    filter_by_okved,
    run_filter_pipeline,
)
from aggregators.sonko.xlsx_parser import parse_xlsx

FIXTURE_PATH = os.path.join(
    os.path.dirname(__file__), "fixtures", "sonko_sample.xlsx"
)


@pytest.fixture
def all_entries() -> list[SONKOEntry]:
    return parse_xlsx(FIXTURE_PATH)


class TestOkvedFilter:
    def test_keeps_87_88(self, all_entries: list[SONKOEntry]):
        filtered = filter_by_okved(all_entries)
        for e in filtered:
            assert e.okved_prefix in ("87", "88")

    def test_counts_correct(self, all_entries: list[SONKOEntry]):
        filtered = filter_by_okved(all_entries)
        # Rows: 0,1 (88.10), 2 (87.30), 5 (88.99) = 4 entries
        assert len(filtered) == 4


class TestNameKeywordFilter:
    def test_matches_elderly_keywords(self):
        test_cases = [
            ("ОРГАНИЗАЦИЯ ВЕТЕРАНОВ ВОЙНЫ", True),
            ("ПАНСИОНАТ ДЛЯ ПРЕСТАРЕЛЫХ", True),
            ("ФОНД ГЕРОНТОЛОГИЧЕСКИХ ИССЛЕДОВАНИЙ", True),
            ("ЦЕНТР СОЦИАЛЬНОГО ОБСЛУЖИВАНИЯ", True),
            ("АНО РЕАБИЛИТАЦИИ ИНВАЛИДОВ", True),
            ("ШКОЛА БИЗНЕСА", False),
            ("ЭКОЛОГИЧЕСКАЯ ИНИЦИАТИВА", False),
            ("БЛАГОТВОРИТЕЛЬНЫЙ ФОНД ПОМОЩИ СЕМЬЯМ", False),
        ]
        for name, expected in test_cases:
            result = bool(ELDERLY_PATTERN.search(name))
            assert result == expected, f"'{name}': expected {expected}, got {result}"

    def test_filter_from_sample(self, all_entries: list[SONKOEntry]):
        filtered = filter_by_name_keywords(all_entries)
        # Entries with elderly names: row 2 (престарелых), row 3 (ветеранов/пенсионеров), row 6 (геронтологических)
        names = {e.full_name for e in filtered}
        assert any("ПРЕСТАРЕЛ" in n for n in names)
        assert any("ВЕТЕРАН" in n for n in names)
        assert any("ГЕРОНТО" in n.upper() for n in names)


class TestDedup:
    def test_groups_by_inn(self, all_entries: list[SONKOEntry]):
        orgs = deduplicate_by_inn(all_entries)
        inns = [o.inn for o in orgs]
        # INN 7701234567 appears twice, should become 1 org with 2 entries
        assert inns.count("7701234567") == 1
        org_with_two = next(o for o in orgs if o.inn == "7701234567")
        assert org_with_two.entry_count == 2

    def test_sorted_by_entry_count(self, all_entries: list[SONKOEntry]):
        orgs = deduplicate_by_inn(all_entries)
        counts = [o.entry_count for o in orgs]
        assert counts == sorted(counts, reverse=True)


class TestFullPipeline:
    def test_end_to_end(self, all_entries: list[SONKOEntry]):
        orgs, stats = run_filter_pipeline(all_entries)

        assert stats.total_entries == 8
        assert stats.after_okved > 0
        assert stats.after_name_kw > 0
        assert stats.combined_unique > 0
        assert stats.combined_unique == len(orgs)
        assert all(isinstance(o, SONKOOrganization) for o in orgs)

    def test_union_filter(self, all_entries: list[SONKOEntry]):
        orgs, stats = run_filter_pipeline(all_entries)
        # Combined should be >= max(okved, name_kw) unique orgs
        assert stats.combined_unique >= max(
            len({e.inn for e in filter_by_okved(all_entries)}),
            len({e.inn for e in filter_by_name_keywords(all_entries)}),
        )

    def test_excludes_irrelevant(self, all_entries: list[SONKOEntry]):
        orgs, _ = run_filter_pipeline(all_entries)
        inns = {o.inn for o in orgs}
        # School of Business (85.42, no keyword) should be excluded
        assert "7700000002" not in inns
        # Ecological initiative (72.19, no keyword) should be excluded
        assert "7700000005" not in inns

    def test_summary_string(self, all_entries: list[SONKOEntry]):
        _, stats = run_filter_pipeline(all_entries)
        summary = stats.summary()
        assert isinstance(summary, str)
        assert "OKVED" in summary

    def test_social_service_provider_property(self, all_entries: list[SONKOEntry]):
        orgs, _ = run_filter_pipeline(all_entries)
        org = next((o for o in orgs if o.inn == "7701234567"), None)
        assert org is not None
        assert org.is_social_service_provider is True
