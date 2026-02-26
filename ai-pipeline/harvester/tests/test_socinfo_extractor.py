"""
Tests for the socinfo.ru markdown extractor.

Uses real snapshots from Sprint 3.6 batch test to validate extraction
accuracy across multiple socinfo.ru KCSON/CSO sites.
"""

import pytest
from pathlib import Path

from strategies.site_extractors import SiteExtractorRegistry
from strategies.site_extractors.socinfo import SocinfoExtractor

FIXTURES = Path(__file__).parent / "fixtures" / "batch_raw"

extractor = SocinfoExtractor()


# ---------------------------------------------------------------------------
# Platform detection
# ---------------------------------------------------------------------------

class TestPlatformDetection:
    def test_socinfo_detected(self):
        assert SiteExtractorRegistry.detect_platform("https://irkcson.aln.socinfo.ru/") == "socinfo"

    def test_subdomain_detected(self):
        assert SiteExtractorRegistry.detect_platform("https://cso-kaltan.kmr.socinfo.ru/contacts") == "socinfo"

    def test_non_socinfo_none(self):
        assert SiteExtractorRegistry.detect_platform("https://example.com") is None

    def test_partial_match_none(self):
        assert SiteExtractorRegistry.detect_platform("https://socinfo.ru") is None

    def test_extract_if_known_returns_dict(self):
        md = "[На главную - socinfo.ru]\nОрганизация\n## Адрес\n123456, г. Тест"
        result = SiteExtractorRegistry.extract_if_known("https://test.kmr.socinfo.ru/", md)
        assert result is not None
        assert result["platform"] == "socinfo.ru"

    def test_extract_if_known_non_socinfo(self):
        result = SiteExtractorRegistry.extract_if_known("https://example.com", "text")
        assert result is None


# ---------------------------------------------------------------------------
# Title extraction
# ---------------------------------------------------------------------------

class TestTitleExtraction:

    def test_irkcson_title(self):
        md = _load("irkcson.aln.socinfo.ru_page.txt")
        r = extractor.extract(md)
        assert "Комплексный центр социального обслуживания" in r["title"]
        assert "Иристонского района" in r["title"]

    def test_kaltan_title(self):
        md = _load("cso-kaltan.kmr.socinfo.ru_page.txt")
        r = extractor.extract(md)
        assert "Центр социального обслуживания населения" in r["title"]

    def test_kcson_stv_title(self):
        md = _load("kcson.stv.socinfo.ru_page.txt")
        r = extractor.extract(md)
        assert "Курский центр" in r["title"] or "социального обслуживания" in r["title"]

    def test_kcson_kr_title(self):
        md = _load("kcson-kr.adg.socinfo.ru_page.txt")
        r = extractor.extract(md)
        assert "Красногвардейский" in r["title"]


# ---------------------------------------------------------------------------
# Short title (from footer ©)
# ---------------------------------------------------------------------------

class TestShortTitle:

    def test_irkcson_short(self):
        md = _load("irkcson.aln.socinfo.ru_page.txt")
        r = extractor.extract(md)
        assert "Комплексный центр" in r["short_title"] or "Иристонского" in r["short_title"]

    def test_kaltan_short(self):
        md = _load("cso-kaltan.kmr.socinfo.ru_page.txt")
        r = extractor.extract(md)
        assert "Центр социального обслуживания" in r["short_title"]


# ---------------------------------------------------------------------------
# Address extraction
# ---------------------------------------------------------------------------

class TestAddressExtraction:

    def test_irkcson_address(self):
        md = _load("irkcson.aln.socinfo.ru_page.txt")
        r = extractor.extract(md)
        assert "362025" in r["address_raw"]
        assert "Ватутина" in r["address_raw"]

    def test_kaltan_address(self):
        md = _load("cso-kaltan.kmr.socinfo.ru_page.txt")
        r = extractor.extract(md)
        assert "652740" in r["address_raw"]
        assert "Горького" in r["address_raw"]

    def test_kcson_stv_address(self):
        md = _load("kcson.stv.socinfo.ru_page.txt")
        r = extractor.extract(md)
        assert "357850" in r["address_raw"] or "Ставропольский" in r["address_raw"]

    def test_kcson_kr_address(self):
        md = _load("kcson-kr.adg.socinfo.ru_page.txt")
        r = extractor.extract(md)
        assert "385300" in r["address_raw"]
        assert "Заринского" in r["address_raw"]

    def test_alagir_contacts_page(self):
        md = _load("kcso-alagir.aln.socinfo.ru_contacts_page.txt")
        r = extractor.extract(md)
        assert "363240" in r["address_raw"] or "Комсомольская" in r["address_raw"]


# ---------------------------------------------------------------------------
# Phone extraction
# ---------------------------------------------------------------------------

class TestPhoneExtraction:

    def test_irkcson_phone(self):
        md = _load("irkcson.aln.socinfo.ru_page.txt")
        r = extractor.extract(md)
        assert len(r["phones"]) >= 1
        phones_joined = " ".join(r["phones"])
        assert "8672" in phones_joined or "30-30-93" in phones_joined

    def test_kaltan_phone(self):
        md = _load("cso-kaltan.kmr.socinfo.ru_page.txt")
        r = extractor.extract(md)
        assert len(r["phones"]) >= 1

    def test_dolzh_contacts_phones(self):
        md = _load("csondolzh.orl.socinfo.ru_contacts_page.txt")
        r = extractor.extract(md)
        assert len(r["phones"]) >= 3


# ---------------------------------------------------------------------------
# Email extraction
# ---------------------------------------------------------------------------

class TestEmailExtraction:

    def test_kcson_stv_email(self):
        md = _load("kcson.stv.socinfo.ru_page.txt")
        r = extractor.extract(md)
        assert any("cson14" in e or "minsoc26" in e for e in r["emails"])

    def test_dolzh_email(self):
        md = _load("csondolzh.orl.socinfo.ru_contacts_page.txt")
        r = extractor.extract(md)
        assert any("orel-region" in e for e in r["emails"])

    def test_noise_emails_filtered(self):
        md = "email: test@socinfo.ru and mintrud_ra@mail.ru and real@example.org"
        r = extractor.extract(md)
        assert "test@socinfo.ru" not in [e.lower() for e in r["emails"]]
        assert "mintrud_ra@mail.ru" not in [e.lower() for e in r["emails"]]


# ---------------------------------------------------------------------------
# Director extraction
# ---------------------------------------------------------------------------

class TestDirectorExtraction:

    def test_alagir_director(self):
        md = _load("kcso-alagir.aln.socinfo.ru_contacts_page.txt")
        r = extractor.extract(md)
        assert "Бутаев" in r["director"]

    def test_kcson_kr_director(self):
        md = _load("kcson-kr.adg.socinfo.ru_page.txt")
        r = extractor.extract(md)
        assert "Гавриш" in r["director"]


# ---------------------------------------------------------------------------
# Work schedule extraction
# ---------------------------------------------------------------------------

class TestScheduleExtraction:

    def test_kcson_stv_schedule(self):
        md = _load("kcson.stv.socinfo.ru_page.txt")
        r = extractor.extract(md)
        assert "8:00" in r["work_schedule"] or "понедельник" in r["work_schedule"].lower()

    def test_kcson_kr_schedule(self):
        md = _load("kcson-kr.adg.socinfo.ru_page.txt")
        r = extractor.extract(md)
        assert "8.00" in r["work_schedule"] or "17.00" in r["work_schedule"]


# ---------------------------------------------------------------------------
# Description extraction
# ---------------------------------------------------------------------------

class TestDescriptionExtraction:

    def test_irkcson_description(self):
        md = _load("irkcson.aln.socinfo.ru_page.txt")
        r = extractor.extract(md)
        assert "социальн" in r["description"].lower()
        assert len(r["description"]) > 100

    def test_kaltan_description(self):
        md = _load("cso-kaltan.kmr.socinfo.ru_page.txt")
        r = extractor.extract(md)
        assert "Добро пожаловать" in r["description"] or "учреждени" in r["description"].lower()


# ---------------------------------------------------------------------------
# Social links
# ---------------------------------------------------------------------------

class TestSocialLinks:

    def test_dolzh_vk(self):
        md = _load("csondolzh.orl.socinfo.ru_contacts_page.txt")
        r = extractor.extract(md)
        assert "vk.com/cson57" in r["vk_url"]

    def test_dolzh_ok(self):
        md = _load("csondolzh.orl.socinfo.ru_contacts_page.txt")
        r = extractor.extract(md)
        assert "ok.ru/cson57" in r["ok_url"]


# ---------------------------------------------------------------------------
# Condensed text for enrichment pipeline (H11)
# ---------------------------------------------------------------------------

class TestBuildCondensedText:
    """Tests for _build_condensed_text used in EnrichmentPipeline._try_site_extractor."""

    def test_full_fields(self):
        from search.enrichment_pipeline import _build_condensed_text

        fields = {
            "platform": "socinfo.ru",
            "title": "КЦСОН Тестового района",
            "short_title": "КЦСОН Тест",
            "address_raw": "123456, г. Тест, ул. Ленина, 1",
            "phones": ["+7(123)456-78-90", "+7(123)456-78-91"],
            "emails": ["test@kcson.ru"],
            "director": "Иванов И.И.",
            "work_schedule": "пн-пт 9:00-18:00",
            "description": "Центр социального обслуживания населения.",
            "vk_url": "https://vk.com/kcson_test",
            "ok_url": "",
        }
        result = _build_condensed_text(fields, "https://kcson.test.socinfo.ru/")

        assert "КЦСОН Тестового района" in result
        assert "КЦСОН Тест" in result
        assert "123456" in result
        assert "+7(123)456-78-90" in result
        assert "test@kcson.ru" in result
        assert "Иванов И.И." in result
        assert "пн-пт" in result
        assert "vk.com/kcson_test" in result
        assert "ok.ru" not in result
        assert len(result) < 1000

    def test_minimal_fields(self):
        from search.enrichment_pipeline import _build_condensed_text

        fields = {"platform": "socinfo.ru", "title": "Тестовая организация"}
        result = _build_condensed_text(fields, "https://test.socinfo.ru/")

        assert "Тестовая организация" in result
        assert "test.socinfo.ru" in result

    def test_try_site_extractor_socinfo(self):
        from search.enrichment_pipeline import EnrichmentPipeline

        md = "[На главную - socinfo.ru]\n[![](logo.png)](https://test.socinfo.ru)\nМБУ «КЦСОН г. Тестов»\n## Адрес\n123456, г. Тестов"
        result = EnrichmentPipeline._try_site_extractor(
            "https://test.kmr.socinfo.ru/", md,
        )
        assert "МБУ «КЦСОН г. Тестов»" in result
        assert len(result) < len(md) or len(md) < 500

    def test_try_site_extractor_unknown_platform(self):
        from search.enrichment_pipeline import EnrichmentPipeline

        md = "Some random website content " * 100
        result = EnrichmentPipeline._try_site_extractor(
            "https://example.com", md,
        )
        assert result == md[:30000]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load(filename: str) -> str:
    path = FIXTURES / filename
    if not path.exists():
        pytest.skip(f"Fixture not found: {filename}")
    return path.read_text(encoding="utf-8")
