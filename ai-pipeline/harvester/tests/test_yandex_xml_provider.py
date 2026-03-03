"""Tests for YandexSearchProvider — XML parsing, error handling, config.

Provider uses Yandex Cloud Search API v2 with Api-Key auth
(service account + scope yc.search-api.execute).
"""

import pytest

from search.yandex_xml_provider import (
    YandexSearchProvider,
    _parse_yandex_xml,
    _strip_hl,
)


SAMPLE_XML_RESPONSE = """\
<?xml version="1.0" encoding="utf-8"?>
<yandexsearch version="1.0">
<request>
  <query>ГАУСО ЧПНДИ Чита сайт</query>
  <page>0</page>
  <sortby order="descending" priority="no">rlv</sortby>
  <groupings>
    <groupby attr="d" mode="deep" groups-on-page="10" docs-in-group="1" curcateg="-1"/>
  </groupings>
</request>
<response date="20260224T120000">
  <reqid>test-reqid-12345</reqid>
  <found priority="all">3</found>
  <results>
    <grouping attr="d" mode="deep" groups-on-page="10" docs-in-group="1" curcateg="-1">
      <found priority="all">3</found>
      <found-docs priority="all">3</found-docs>
      <page first="1" last="3">0</page>
      <group>
        <categ attr="d" name="chita-pndi.zabguso.ru"/>
        <doc id="DOC1">
          <url>https://chita-pndi.zabguso.ru/</url>
          <domain>chita-pndi.zabguso.ru</domain>
          <title><hlword>ГАУСО</hlword> <hlword>ЧПНДИ</hlword> - официальный сайт</title>
          <passages>
            <passage>Государственное учреждение <hlword>ЧПНДИ</hlword> города Читы</passage>
          </passages>
        </doc>
      </group>
      <group>
        <categ attr="d" name="vk.com"/>
        <doc id="DOC2">
          <url>https://vk.com/chitapndi</url>
          <domain>vk.com</domain>
          <title>ЧПНДИ | ВКонтакте</title>
          <passages>
            <passage>Страница учреждения в ВК</passage>
          </passages>
        </doc>
      </group>
      <group>
        <categ attr="d" name="zabguso.ru"/>
        <doc id="DOC3">
          <url>https://zabguso.ru/organizations/chita-pndi</url>
          <domain>zabguso.ru</domain>
          <title>Список учреждений</title>
          <passages/>
        </doc>
      </group>
    </grouping>
  </results>
</response>
</yandexsearch>
"""

EMPTY_RESULTS_XML = """\
<?xml version="1.0" encoding="utf-8"?>
<yandexsearch version="1.0">
<response date="20260224T120000">
  <error code="15">Sorry, there are no results for this search</error>
</response>
</yandexsearch>
"""

ERROR_XML = """\
<?xml version="1.0" encoding="utf-8"?>
<yandexsearch version="1.0">
<response date="20260224T120000">
  <error code="33">API key not valid</error>
</response>
</yandexsearch>
"""


class TestStripHl:
    def test_removes_tags(self):
        assert _strip_hl("<hlword>test</hlword>") == "test"

    def test_removes_multiple(self):
        assert _strip_hl("a <hlword>b</hlword> c <hlword>d</hlword>") == "a b c d"

    def test_no_tags(self):
        assert _strip_hl("plain text") == "plain text"


class TestParseYandexXml:
    def test_parses_three_results(self):
        results = _parse_yandex_xml(SAMPLE_XML_RESPONSE)
        assert len(results) == 3

    def test_first_result_url(self):
        results = _parse_yandex_xml(SAMPLE_XML_RESPONSE)
        assert results[0].url == "https://chita-pndi.zabguso.ru/"

    def test_first_result_title_stripped(self):
        results = _parse_yandex_xml(SAMPLE_XML_RESPONSE)
        assert "ГАУСО" in results[0].title
        assert "<hlword>" not in results[0].title

    def test_first_result_snippet(self):
        results = _parse_yandex_xml(SAMPLE_XML_RESPONSE)
        assert "ЧПНДИ" in results[0].snippet
        assert "<hlword>" not in results[0].snippet

    def test_positions_sequential(self):
        results = _parse_yandex_xml(SAMPLE_XML_RESPONSE)
        assert [r.position for r in results] == [1, 2, 3]

    def test_engine_tag(self):
        results = _parse_yandex_xml(SAMPLE_XML_RESPONSE)
        assert all(r.source_engine == "yandex" for r in results)

    def test_empty_results(self):
        results = _parse_yandex_xml(EMPTY_RESULTS_XML)
        assert results == []

    def test_error_raises(self):
        with pytest.raises(RuntimeError, match="API key not valid"):
            _parse_yandex_xml(ERROR_XML)

    def test_third_result_empty_snippet(self):
        results = _parse_yandex_xml(SAMPLE_XML_RESPONSE)
        assert results[2].snippet == ""


class TestProviderConfig:
    def test_not_configured_by_default(self, monkeypatch):
        monkeypatch.delenv("YANDEX_SEARCH_FOLDER_ID", raising=False)
        monkeypatch.delenv("YANDEX_SEARCH_API_KEY", raising=False)
        p = YandexSearchProvider(folder_id="", api_key="")
        assert not p.is_configured

    def test_configured_with_creds(self):
        p = YandexSearchProvider(folder_id="abc", api_key="xyz")
        assert p.is_configured

    def test_engine_name(self):
        p = YandexSearchProvider(folder_id="a", api_key="b")
        assert p.engine_name == "yandex"

    def test_auth_headers(self):
        p = YandexSearchProvider(folder_id="f", api_key="AQVN1234secret")
        headers = p._auth_headers()
        assert headers["Authorization"] == "Api-Key AQVN1234secret"

    @pytest.mark.asyncio
    async def test_search_raises_without_creds(self, monkeypatch):
        monkeypatch.delenv("YANDEX_SEARCH_FOLDER_ID", raising=False)
        monkeypatch.delenv("YANDEX_SEARCH_API_KEY", raising=False)
        p = YandexSearchProvider(folder_id="", api_key="")
        with pytest.raises(RuntimeError, match="YANDEX_SEARCH_FOLDER_ID"):
            await p.search("test")
