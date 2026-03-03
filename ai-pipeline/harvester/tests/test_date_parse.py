"""Tests for utils.date_parse (Russian date_text -> start/end ISO)."""

import pytest

from utils.date_parse import parse_date_text_to_iso


def test_parse_full_datetime_range():
    text = "28 февраля 2025 (пятница), 10.00 - 11.30 (Мск)"
    start, end = parse_date_text_to_iso(text)
    assert start == "2025-02-28T10:00:00+03:00"
    assert end == "2025-02-28T11:30:00+03:00"


def test_parse_date_with_colon_time():
    text = "1 июля, 10:00 - 11:30 (Мск)"
    start, end = parse_date_text_to_iso(text)
    assert start is not None
    assert end is not None
    assert "07-01" in start
    assert "10:00" in start
    assert "11:30" in end


def test_parse_single_time():
    text = "27 мая 2025 года в 11:00 (мск)"
    start, end = parse_date_text_to_iso(text)
    assert start == "2025-05-27T11:00:00+03:00"
    assert end is not None
    assert "12:00" in end


def test_parse_empty_returns_none():
    assert parse_date_text_to_iso("") == (None, None)
    assert parse_date_text_to_iso("   ") == (None, None)


def test_parse_no_month_returns_none():
    start, end = parse_date_text_to_iso("some text without date")
    assert start is None
    assert end is None
