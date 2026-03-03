"""
Integration test: OrganizationProcessor + real DeepSeek API.

Skipped automatically when DEEPSEEK_API_KEY is not set.
Run explicitly:
    DEEPSEEK_API_KEY=<key> python -m pytest tests/test_integration_deepseek.py -v

Validates:
  - End-to-end classification of 3 URLs (fixture markdowns)
  - Cache hit rate on repeated system prompt
  - Output schema compliance
  - Decision quality (confidence, works_with_elderly)
"""

import pytest

from config.settings import get_settings

settings = get_settings()
DEEPSEEK_KEY = settings.deepseek_api_key or ""
skip_no_key = pytest.mark.skipif(
    not DEEPSEEK_KEY or "your" in DEEPSEEK_KEY.lower(),
    reason="DEEPSEEK_API_KEY not set — skipping integration test",
)

FIXTURE_KCSON = """
# КЦСОН Вологодского муниципального округа
Комплексный центр социального обслуживания населения Вологодского муниципального округа.
**Адрес:** г. Вологда, ул. Пушкинская, д. 18
**Телефон:** 8 (8172) 75-15-45
**Email:** kcson-vol@mail.ru
## Услуги
- Социальное обслуживание на дому граждан пожилого возраста
- Срочное социальное обслуживание
- Консультативная помощь
## О нас
Мы оказываем комплексные социальные услуги гражданам пожилого возраста и инвалидам.
ИНН: 3525123456, ОГРН: 1023500870240
"""

FIXTURE_KINDERGARTEN = """
# Детский сад «Солнышко» №15
Муниципальное бюджетное дошкольное образовательное учреждение.
**Адрес:** г. Москва, ул. Ленина, д. 5
**Телефон:** 8 (495) 123-45-67
## Направления
- Группы раннего развития (1-3 года)
- Дошкольное образование (3-7 лет)
- Подготовка к школе
ИНН: 7701234567
"""

FIXTURE_NKO = """
# АНО «Старшее поколение»
Автономная некоммерческая организация помощи пожилым людям.
**Адрес:** г. Санкт-Петербург, пр. Невский, д. 100
**Телефон:** 8 (812) 999-88-77
## Деятельность
- Организация досуга для пенсионеров
- Компьютерные курсы для пожилых
- Школа здоровья 55+
- Юридические консультации для граждан старшего возраста
"""


@skip_no_key
class TestOrganizationProcessorIntegration:

    @pytest.fixture(autouse=True)
    def setup_processor(self):
        from processors.deepseek_client import DeepSeekClient
        from processors.organization_processor import OrganizationProcessor

        self.client = DeepSeekClient(api_key=DEEPSEEK_KEY)
        self.processor = OrganizationProcessor(deepseek_client=self.client)

    def _process(self, markdown: str, url: str = "https://example.com"):
        from prompts.schemas import EntityType, HarvestInput

        harvest_input = HarvestInput(
            source_id="integration-test",
            source_item_id=url,
            entity_type=EntityType.ORGANIZATION,
            raw_text=markdown,
            source_url=url,
            source_kind="org_website",
        )
        return self.processor.process(harvest_input)

    def test_kcson_accepted(self):
        result = self._process(FIXTURE_KCSON, "https://kcson-vol.ru")
        assert result.ai_metadata.decision == "accepted"
        assert result.ai_metadata.works_with_elderly is True
        assert result.ai_metadata.ai_confidence_score >= 0.80
        assert result.title
        assert len(result.venues) >= 1

    def test_kindergarten_rejected(self):
        result = self._process(FIXTURE_KINDERGARTEN, "https://ds15.edu.ru")
        assert result.ai_metadata.decision == "rejected"
        assert result.ai_metadata.works_with_elderly is False
        assert result.ai_metadata.ai_confidence_score <= 0.30

    def test_nko_accepted(self):
        result = self._process(FIXTURE_NKO, "https://starshee-pokolenie.ru")
        assert result.ai_metadata.decision == "accepted"
        assert result.ai_metadata.works_with_elderly is True
        assert result.ai_metadata.ai_confidence_score >= 0.70

    def test_cache_hit_rate(self):
        """After 3 classifications, cache hit rate should be > 0 (system prompt cached)."""
        self._process(FIXTURE_KCSON, "https://test1.ru")
        self._process(FIXTURE_NKO, "https://test2.ru")
        self._process(FIXTURE_KINDERGARTEN, "https://test3.ru")

        metrics = self.client.get_metrics()
        assert metrics["total_calls"] >= 3
        assert metrics["cache_hit_rate"] > 0, (
            f"Expected cache hits after 3 calls, got rate={metrics['cache_hit_rate']}"
        )

    def test_output_schema_complete(self):
        result = self._process(FIXTURE_KCSON, "https://schema-test.ru")
        from processors.organization_processor import to_core_import_payload

        payload = to_core_import_payload(result)
        assert "source_reference" in payload
        assert "entity_type" in payload
        assert "ai_metadata" in payload
        assert "classification" in payload
        assert payload["ai_metadata"]["ai_confidence_score"] >= 0
        assert payload["ai_metadata"]["ai_confidence_score"] <= 1
