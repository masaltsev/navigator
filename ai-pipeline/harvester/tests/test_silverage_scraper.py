"""Tests for Silver Age scraper (silveragemap.ru)."""

import pytest

from aggregators.silverage.models import (
    SilverAgeEvent,
    SilverAgeOrganization,
    SilverAgePractice,
)
from aggregators.silverage.scraper import SilverAgeScraper


PRACTICE_LIST_HTML = """
<html><body>
<div class="right_container">
    <div class="project_block">
        <a href='/poisk-proekta/kulinarnaya-studiya-vkus-zhizni/' onclick="">
        <div class="preview_img"><img src="/img/1.png" alt=""></div>
        <div class="description">
            <div class='icon_project_container'>
                <div class="icon_project  backcolor_business"></div>
                <div class="icon_project  backcolor_care"></div>
            </div>
            <p class="desc_title">Кулинарная студия "Вкус жизни"</p>
            <p>Описание кулинарной студии</p>
        </div>
        <div class="region_project">Костромская область</div>
        </a>
    </div>
    <div class="project_block">
        <a href='/poisk-proekta/vtoroe-dykhanie/' onclick="">
        <div class="preview_img"><img src="/img/2.png" alt=""></div>
        <div class="description">
            <div class='icon_project_container'>
                <div class="icon_project  backcolor_sport"></div>
            </div>
            <p class="desc_title">Второе дыхание</p>
            <p>Вовлечение людей старшего возраста</p>
        </div>
        <div class="region_project">Самарская область</div>
        </a>
    </div>
    <div class="project_block">
        <a href='/poisk-proekta/form/' onclick="">
        <div class="preview_img"></div>
        <div class="description"><p>Отправить практику</p></div>
        </a>
    </div>
</div>
<div class="project_navigation">
    <a href="?PAGEN_1=2">2</a>
    <a href="?PAGEN_1=3">3</a>
    <a href="?PAGEN_1=65">65</a>
</div>
</body></html>
"""


PRACTICE_DETAIL_HTML = """
<html><body>
<div class="containerPage">
    <h1>Кулинарная студия "Вкус жизни"</h1>
    <div class="content">
        <div class="region_info">
            <div class="info_top">
                <div><b>География проекта</b></div>
                <div class="region">Костромская область</div>
            </div>
            <div class="info_middle">
                <div><b>Сроки проведения</b></div>
                <div class="data">12.01.2026 — 12.01.2027</div>
            </div>
            <div class="info_bottom">
                <a data-fancybox href='#info_popup'>
                    <span class="information">Информация об организации</span>
                </a>
            </div>
            <div class='icon_project_container'>
                <div class="icon_project  backcolor_sport"></div>
                <div class="icon_project  backcolor_educ"></div>
                <div class="icon_project  backcolor_care"></div>
            </div>
        </div>
        Представьте: человек прожил долгую жизнь, готовил для семьи.
        Это реабилитационная практика для пожилых людей.
    </div>
</div>
<div id='info_popup'>ОГБУ «Октябрьский геронтологический центр» (ОГБУ «Октябрьский ГЦ») основано в 1978 году, является учреждением стационарного типа для пожилых людей.

naukaipf@mail.ru
+7 963 218-26-63
https://vk.com/ogc44rus?from=groups
https://ogc44.ru</div>
</body></html>
"""


EVENT_LIST_HTML = """
<html><body>
<div class="content">
    <h1>Мероприятия</h1>
    <div class="event_block">
        <a href="/meropriyatiya/podvedenie-itogov-aktsii-priznanie-2025/">Подробнее</a>
    </div>
    <div class="event_block">
        <a href="/meropriyatiya/ekspertnyy-vzglyad/">Подробнее</a>
    </div>
</div>
</body></html>
"""


EVENT_DETAIL_HTML = """
<html><body>
<div class="containerPage">
    <div class="containerProject">
        <div class="containerProject_left">
            <div class="titlePage">Подведение итогов акции "Признание 2025"</div>
            <ul class="newsTag_container">
                <li class="newsTag">Мероприятия Коалиции</li>
            </ul>
            <div class="containerProject-content">
                Дорогие друзья! Акция признания «Забота рядом» — 2025 завершилась.
            </div>
        </div>
        <aside class="info_project">
            <div class="region_info">
                <div><b>Место проведения</b></div>
                <div>Онлайн</div>
                <div><b>Сроки проведения</b></div>
                <div>16 мая 10:00–11:30 (МСК)</div>
                <div><a href="https://koalitsiya-nko-zabota-rya.timepad.ru/event/3348497/">Записаться</a></div>
            </div>
        </aside>
    </div>
</div>
<h2 class="titleDetail">Другие мероприятия</h2>
</body></html>
"""


class TestPracticeListParser:
    def test_extracts_practice_slugs(self):
        scraper = SilverAgeScraper()
        slugs = scraper._parse_practice_list(PRACTICE_LIST_HTML)
        assert "kulinarnaya-studiya-vkus-zhizni" in slugs
        assert "vtoroe-dykhanie" in slugs

    def test_excludes_form_and_search(self):
        scraper = SilverAgeScraper()
        slugs = scraper._parse_practice_list(PRACTICE_LIST_HTML)
        assert "form" not in slugs
        assert "search" not in slugs

    def test_finds_max_page(self):
        scraper = SilverAgeScraper()
        max_page = scraper._find_max_page(PRACTICE_LIST_HTML)
        assert max_page == 65

    def test_no_pagination(self):
        scraper = SilverAgeScraper()
        max_page = scraper._find_max_page("<html><body>No pages</body></html>")
        assert max_page == 1


class TestPracticeDetailParser:
    def test_parses_title(self):
        scraper = SilverAgeScraper()
        practice = scraper._parse_practice_detail(PRACTICE_DETAIL_HTML, "kulinarnaya-studiya-vkus-zhizni")
        assert practice is not None
        assert practice.title == 'Кулинарная студия "Вкус жизни"'

    def test_parses_region(self):
        scraper = SilverAgeScraper()
        practice = scraper._parse_practice_detail(PRACTICE_DETAIL_HTML, "test-slug")
        assert practice is not None
        assert practice.region == "Костромская область"

    def test_parses_dates(self):
        scraper = SilverAgeScraper()
        practice = scraper._parse_practice_detail(PRACTICE_DETAIL_HTML, "test-slug")
        assert practice is not None
        assert "12.01.2026" in practice.dates

    def test_parses_categories(self):
        scraper = SilverAgeScraper()
        practice = scraper._parse_practice_detail(PRACTICE_DETAIL_HTML, "test-slug")
        assert practice is not None
        assert "Связь поколений" in practice.categories
        assert "Обучение" in practice.categories
        assert "Забота рядом" in practice.categories

    def test_parses_org_info(self):
        scraper = SilverAgeScraper()
        practice = scraper._parse_practice_detail(PRACTICE_DETAIL_HTML, "test-slug")
        assert practice is not None
        assert "ОГБУ" in practice.org_name
        assert practice.org_email == "naukaipf@mail.ru"
        assert practice.org_phone == "+7 963 218-26-63"
        assert practice.org_vk == "https://vk.com/ogc44rus?from=groups"
        assert practice.org_website == "https://ogc44.ru"

    def test_generates_page_url(self):
        scraper = SilverAgeScraper()
        practice = scraper._parse_practice_detail(PRACTICE_DETAIL_HTML, "kulinarnaya-studiya")
        assert practice is not None
        assert practice.page_url == "https://silveragemap.ru/poisk-proekta/kulinarnaya-studiya/"

    def test_source_reference(self):
        practice = SilverAgePractice(
            slug="kulinarnaya-studiya-vkus-zhizni",
            title="Test",
        )
        assert practice.source_reference == "silverage_practice_kulinarnaya-studiya-vkus-zhizni"

    def test_returns_none_for_empty_html(self):
        scraper = SilverAgeScraper()
        result = scraper._parse_practice_detail("<html><body></body></html>", "slug")
        assert result is None


class TestOrgInfoExtraction:
    def test_extracts_email_phone_links(self):
        scraper = SilverAgeScraper()
        info = scraper._extract_org_info(PRACTICE_DETAIL_HTML)
        assert info["org_email"] == "naukaipf@mail.ru"
        assert info["org_phone"] == "+7 963 218-26-63"
        assert info["org_vk"] == "https://vk.com/ogc44rus?from=groups"
        assert info["org_website"] == "https://ogc44.ru"

    def test_no_info_popup(self):
        scraper = SilverAgeScraper()
        info = scraper._extract_org_info("<html><body>No popup</body></html>")
        assert info["org_name"] == ""
        assert info["org_email"] == ""

    def test_social_links_collected(self):
        scraper = SilverAgeScraper()
        info = scraper._extract_org_info(PRACTICE_DETAIL_HTML)
        assert len(info["org_social_links"]) >= 2


class TestEventListParser:
    def test_extracts_event_slugs(self):
        scraper = SilverAgeScraper()
        slugs = scraper._parse_events_list(EVENT_LIST_HTML)
        assert "podvedenie-itogov-aktsii-priznanie-2025" in slugs
        assert "ekspertnyy-vzglyad" in slugs

    def test_deduplicates_slugs(self):
        html = """
        <a href="/meropriyatiya/some-event/">Link 1</a>
        <a href="/meropriyatiya/some-event/">Link 2</a>
        """
        scraper = SilverAgeScraper()
        slugs = scraper._parse_events_list(html)
        assert slugs.count("some-event") == 1


class TestEventDetailParser:
    def test_parses_title(self):
        scraper = SilverAgeScraper()
        event = scraper._parse_event_detail(EVENT_DETAIL_HTML, "priznanie-2025")
        assert event is not None
        assert "Признание 2025" in event.title

    def test_parses_registration_url(self):
        scraper = SilverAgeScraper()
        event = scraper._parse_event_detail(EVENT_DETAIL_HTML, "priznanie-2025")
        assert event is not None
        assert event.registration_url is not None
        assert "timepad.ru" in event.registration_url

    def test_parses_page_url(self):
        scraper = SilverAgeScraper()
        event = scraper._parse_event_detail(EVENT_DETAIL_HTML, "prizn-2025")
        assert event is not None
        assert event.page_url == "https://silveragemap.ru/meropriyatiya/prizn-2025/"

    def test_parses_category(self):
        scraper = SilverAgeScraper()
        event = scraper._parse_event_detail(EVENT_DETAIL_HTML, "prizn-2025")
        assert event is not None
        assert event.category == "Мероприятия Коалиции"

    def test_parses_description(self):
        scraper = SilverAgeScraper()
        event = scraper._parse_event_detail(EVENT_DETAIL_HTML, "prizn-2025")
        assert event is not None
        assert "Забота рядом" in event.description

    def test_is_online(self):
        event = SilverAgeEvent(slug="test", title="Test", location="Онлайн")
        assert event.is_online is True

    def test_is_not_online(self):
        event = SilverAgeEvent(slug="test", title="Test", location="Москва")
        assert event.is_online is False


class TestModels:
    def test_organization_properties(self):
        p1 = SilverAgePractice(
            slug="p1", title="Practice 1",
            categories=["Обучение", "Забота рядом"],
            full_description="Short",
        )
        p2 = SilverAgePractice(
            slug="p2", title="Practice 2",
            categories=["Обучение", "Психология"],
            full_description="This is a much longer description of the practice",
        )
        org = SilverAgeOrganization(
            name="Test Org",
            description="Org desc",
            practices=[p1, p2],
        )
        assert org.practice_count == 2
        assert org.all_categories == {"Обучение", "Забота рядом", "Психология"}
        assert org.best_description == "This is a much longer description of the practice"

    def test_event_source_reference(self):
        event = SilverAgeEvent(slug="some-event-slug", title="Test")
        assert event.source_reference == "silverage_event_some-event-slug"
