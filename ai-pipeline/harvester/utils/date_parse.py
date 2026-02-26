"""
Parse Russian human-readable date/time strings into ISO datetime for API.

Used for Silver Age and other aggregators where date_text is like:
  "28 февраля 2025 (пятница), 10.00 - 11.30 (Мск)"
  "1 июля, 10:00 - 11:30 (Мск)"
  "27 мая 2025 года в 11:00 (мск)"

Returns (start_datetime_iso, end_datetime_iso) or (None, None) on failure.
Default timezone: Europe/Moscow (Мск).
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Tuple

# Russian month names (genitive for "28 февраля")
MONTHS_RU = {
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5, "июня": 6,
    "июля": 7, "августа": 8, "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,
}
MONTHS_RU_NOM = {
    "январь": 1, "февраль": 2, "март": 3, "апрель": 4, "май": 5, "июнь": 6,
    "июль": 7, "август": 8, "сентябрь": 9, "октябрь": 10, "ноябрь": 11, "декабрь": 12,
}

# Default Moscow offset for output (we emit ISO with +03:00)
TZ_SUFFIX = "+03:00"


def _parse_time(s: str) -> tuple[int, int] | None:
    """Parse '10:00' or '10.00' -> (10, 0)."""
    s = s.strip()
    if not s:
        return None
    m = re.match(r"(\d{1,2})[.:](\d{2})", s)
    if m:
        return int(m.group(1)), int(m.group(2))
    return None


def _parse_date_and_times(date_text: str) -> Tuple[datetime | None, datetime | None]:
    """
    Parse date_text into start and end datetime (naive, then we add tz for API).
    Returns (start_dt, end_dt) or (None, None).
    """
    if not date_text or not date_text.strip():
        return None, None

    text = date_text.strip().lower()
    now = datetime.now()
    year = now.year
    month = None
    day = None

    # Find year if present (4 digits)
    year_m = re.search(r"\b(20\d{2})\s*год[а]?\b", text)
    if year_m:
        year = int(year_m.group(1))
    else:
        year_m = re.search(r"\b(20\d{2})\b", text)
        if year_m:
            year = int(year_m.group(1))

    # Find month
    for name, num in list(MONTHS_RU.items()) + list(MONTHS_RU_NOM.items()):
        if name in text:
            month = num
            break
    if month is None:
        return None, None

    # Day: "28 февраля" or "28 февраля"
    day_m = re.search(r"(\d{1,2})\s*(?:января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)", text, re.I)
    if day_m:
        day = int(day_m.group(1))
    else:
        # "1 июля" without year nearby
        day_m = re.search(r"^(\d{1,2})\s+", text)
        if day_m:
            day = int(day_m.group(1))

    if day is None or month is None:
        return None, None

    try:
        base_date = datetime(year, month, day)
    except ValueError:
        return None, None

    # Times: "10.00 - 11.30" or "10:00 - 11:30" or "в 11:00"
    start_time = (0, 0)
    end_time = (0, 0)

    time_range = re.search(
        r"(\d{1,2})[.:](\d{2})\s*[-–—]\s*(\d{1,2})[.:](\d{2})",
        text,
    )
    single_time_only = False
    if time_range:
        start_time = (int(time_range.group(1)), int(time_range.group(2)))
        end_time = (int(time_range.group(3)), int(time_range.group(4)))
    else:
        single = re.search(r"(?:в\s+)?(\d{1,2})[.:](\d{2})", text)
        if single:
            start_time = (int(single.group(1)), int(single.group(2)))
            end_time = start_time
            single_time_only = True
        else:
            start_time = (0, 0)
            end_time = (0, 0)

    start_dt = base_date.replace(hour=start_time[0], minute=start_time[1], second=0, microsecond=0)
    end_dt = base_date.replace(hour=end_time[0], minute=end_time[1], second=0, microsecond=0)
    if single_time_only or (end_dt <= start_dt and (end_time[0], end_time[1]) == (start_time[0], start_time[1])):
        from datetime import timedelta
        end_dt = start_dt + timedelta(hours=1)

    return start_dt, end_dt


def parse_date_text_to_iso(date_text: str) -> Tuple[str | None, str | None]:
    """
    Parse Russian date_text into (start_datetime_iso, end_datetime_iso).
    Times are in Moscow (+03:00). Format: 2025-02-28T10:00:00+03:00
    """
    start_dt, end_dt = _parse_date_and_times(date_text)
    if start_dt is None or end_dt is None:
        return None, None
    # Emit ISO with Moscow tz (API expects timestamp with timezone)
    start_iso = start_dt.strftime("%Y-%m-%dT%H:%M:%S") + TZ_SUFFIX
    end_iso = end_dt.strftime("%Y-%m-%dT%H:%M:%S") + TZ_SUFFIX
    return start_iso, end_iso
