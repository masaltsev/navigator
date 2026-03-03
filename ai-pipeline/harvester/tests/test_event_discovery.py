"""Tests for strategies/event_discovery.py — event page discovery and splitting."""

import pytest
from strategies.event_discovery import EventDiscoverer, EventCandidate


class TestFindEventPages:
    """_find_event_pages should detect event URLs from patterns and markdown links."""

    def setup_method(self):
        self.discoverer = EventDiscoverer()

    def test_known_patterns_generated(self):
        pages = self.discoverer._find_event_pages("https://example.com", None)
        urls = [url for url, _ in pages]
        assert "https://example.com/news" in urls
        assert "https://example.com/novosti" in urls
        assert "https://example.com/afisha" in urls
        assert "https://example.com/events" in urls

    def test_markdown_link_discovery(self):
        markdown = """
        [Главная](/)
        [О нас](/o-nas)
        [Новости](/novosti-uchrezhdeniya)
        [Контакты](/kontakty)
        [Афиша мероприятий](/afisha-2026)
        """
        pages = self.discoverer._find_event_pages("https://kcson.ru", markdown)
        urls = [url for url, _ in pages]
        assert any("novosti" in u for u in urls)
        assert any("afisha" in u for u in urls)

    def test_no_duplicate_patterns(self):
        pages = self.discoverer._find_event_pages("https://example.com", None)
        urls = [url for url, _ in pages]
        assert len(urls) == len(set(urls))


class TestSplitByHeadings:
    def setup_method(self):
        self.discoverer = EventDiscoverer()

    def test_heading_split(self):
        md = """
## Масленица в КЦСОН

Приглашаем всех на Масленицу! Блины, песни, хороводы.
Дата: 15 марта 2026
Место: ул. Ленина, 1

## Школа ухода за пожилыми

Обучающий семинар для родственников. Бесплатно.
Каждый вторник в 14:00.

## Тендер на закупку мебели

Объявляется конкурс.
"""
        sections = self.discoverer._split_by_headings(md)
        assert len(sections) >= 2
        titles = [t for t, _ in sections]
        assert any("Масленица" in t for t in titles)
        assert any("Школа ухода" in t for t in titles)

    def test_empty_markdown(self):
        sections = self.discoverer._split_by_headings("")
        assert sections == []

    def test_no_headings_short_text(self):
        sections = self.discoverer._split_by_headings("Short text")
        assert sections == []


class TestSplitIntoEvents:
    def setup_method(self):
        self.discoverer = EventDiscoverer()

    def test_event_with_keyword(self):
        md = """
## Мастер-класс по рисованию

Приглашаем на мастер-класс для пенсионеров.
Дата: 20 марта 2026, 10:00.
"""
        candidates = self.discoverer._split_into_events(md, "https://kcson.ru/news", "Новости")
        assert len(candidates) >= 1
        assert "мастер-класс" in candidates[0].title.lower() or "мастер-класс" in candidates[0].markdown.lower()

    def test_irrelevant_filtered(self):
        md = """
## Тендер на закупку оборудования

Объявляется аукцион. Протокол прилагается. Закупки 2026.
"""
        candidates = self.discoverer._split_into_events(md, "https://kcson.ru/news", "Новости")
        assert len(candidates) == 0

    def test_max_events_limit(self):
        discoverer = EventDiscoverer(max_events_per_page=2)
        events = []
        for i in range(5):
            events.append(f"## Концерт {i}\n\nПриглашаем на концерт! Для пенсионеров. Бесплатно.")
        md = "\n\n".join(events)
        candidates = discoverer._split_into_events(md, "https://a.com/news", "Новости")
        assert len(candidates) <= 2


class TestEventKeywords:
    def setup_method(self):
        self.discoverer = EventDiscoverer()

    def test_has_event_signal_positive(self):
        assert self.discoverer._has_event_signal("Масленица в КЦСОН", "приглашаем всех")
        assert self.discoverer._has_event_signal("Школа ухода", "занятие для родственников")
        assert self.discoverer._has_event_signal("Концерт", "для пенсионеров 55+")

    def test_has_event_signal_negative(self):
        assert not self.discoverer._has_event_signal("О нас", "Наше учреждение работает с 1995 года")
        assert not self.discoverer._has_event_signal("Режим работы", "Пн-Пт 9:00-18:00")


class TestFreshnessEstimation:
    def setup_method(self):
        self.discoverer = EventDiscoverer()

    def test_russian_date(self):
        result = self.discoverer._estimate_freshness("15 января 2026 прошел концерт")
        assert result is not None
        assert isinstance(result, int)

    def test_no_date(self):
        result = self.discoverer._estimate_freshness("Приглашаем на мероприятие")
        assert result is None

    def test_numeric_date(self):
        result = self.discoverer._estimate_freshness("01.02.2026 — семинар")
        assert result is not None


class TestEventDiscoveryResult:
    def test_discover_from_cached_markdown(self):
        discoverer = EventDiscoverer()
        markdowns = {
            "https://kcson.ru/news": """
## Мастер-класс для пенсионеров

Приглашаем на мастер-класс по рукоделию для людей 55+.
Дата: 10 февраля 2026.
Место: ул. Ленина, 5

## Лекция о здоровье

Вебинар о профилактике деменции для старшего поколения.
Каждый четверг в 15:00.
"""
        }
        result = discoverer.discover_from_cached_markdown("https://kcson.ru", markdowns)
        assert result.event_pages_found == 1
        assert len(result.candidates) >= 1
