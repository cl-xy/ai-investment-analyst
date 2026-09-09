"""US equity market (NYSE/Nasdaq) trading-day calendar.

Self-contained, zero-dependency implementation of "is the US stock market
open on this calendar date?". Deliberately avoids pulling in a heavy market
calendar package (pandas-market-calendars drags in pandas) — the digest job
only needs a whole-day open/closed answer, not intraday session times, and
this keeps the free-tier image small.

Scope and limitations (documented on purpose so the caller knows the edges):
- Covers the standard NYSE holiday schedule: New Year's Day, MLK Day,
  Washington's Birthday (Presidents' Day), Good Friday, Memorial Day,
  Juneteenth (observed from 2022), Independence Day, Labor Day,
  Thanksgiving, and Christmas — each with the NYSE weekend-observance rule
  (Saturday holiday -> observed Friday, Sunday holiday -> observed Monday).
- Does NOT model early-close (half) days (e.g. day after Thanksgiving,
  Christmas Eve): those are still trading days, so the digest should fire.
- Does NOT model unscheduled closures (e.g. national days of mourning,
  weather). Those are rare and can't be computed ahead of time; a spurious
  digest on such a day is a benign, acceptable failure mode.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo

_ET_ZONE = ZoneInfo("America/New_York")

# Juneteenth became an NYSE holiday starting in 2022.
_JUNETEENTH_FIRST_YEAR = 2022


def _nth_weekday_of_month(year: int, month: int, weekday: int, n: int) -> date:
    """Return the date of the ``n``-th ``weekday`` (Mon=0..Sun=6) in ``month``.

    E.g. 3rd Monday of January -> _nth_weekday_of_month(year, 1, 0, 3).
    """
    first = date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return first + timedelta(days=offset + 7 * (n - 1))


def _last_weekday_of_month(year: int, month: int, weekday: int) -> date:
    """Return the date of the last ``weekday`` (Mon=0..Sun=6) in ``month``."""
    if month == 12:
        next_month_first = date(year + 1, 1, 1)
    else:
        next_month_first = date(year, month + 1, 1)
    last_day = next_month_first - timedelta(days=1)
    offset = (last_day.weekday() - weekday) % 7
    return last_day - timedelta(days=offset)


def _easter_sunday(year: int) -> date:
    """Compute Easter Sunday using the anonymous Gregorian algorithm.

    Good Friday (an NYSE holiday) is two days before Easter Sunday.
    """
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    m = (32 + 2 * e + 2 * i - h - k) % 7
    n = (a + 11 * h + 22 * m) // 451
    month = (h + m - 7 * n + 114) // 31
    day = ((h + m - 7 * n + 114) % 31) + 1
    return date(year, month, day)


def _observed(holiday: date) -> date:
    """Apply the NYSE weekend-observance rule to a fixed-date holiday.

    Saturday -> observed the preceding Friday; Sunday -> observed the
    following Monday. Weekday holidays are unchanged.
    """
    if holiday.weekday() == 5:  # Saturday
        return holiday - timedelta(days=1)
    if holiday.weekday() == 6:  # Sunday
        return holiday + timedelta(days=1)
    return holiday


@lru_cache(maxsize=32)
def market_holidays(year: int) -> frozenset[date]:
    """Return the set of NYSE full-closure holiday dates for ``year``.

    Cached per year since the set is fixed once computed.
    """
    holidays: set[date] = set()

    # Fixed-date holidays (with weekend observance)
    holidays.add(_observed(date(year, 1, 1)))  # New Year's Day
    holidays.add(_observed(date(year, 7, 4)))  # Independence Day
    holidays.add(_observed(date(year, 12, 25)))  # Christmas Day
    if year >= _JUNETEENTH_FIRST_YEAR:
        holidays.add(_observed(date(year, 6, 19)))  # Juneteenth

    # Floating holidays
    holidays.add(_nth_weekday_of_month(year, 1, 0, 3))  # MLK Day: 3rd Mon Jan
    holidays.add(_nth_weekday_of_month(year, 2, 0, 3))  # Presidents' Day: 3rd Mon Feb
    holidays.add(_last_weekday_of_month(year, 5, 0))  # Memorial Day: last Mon May
    holidays.add(_nth_weekday_of_month(year, 9, 0, 1))  # Labor Day: 1st Mon Sep
    holidays.add(_nth_weekday_of_month(year, 11, 3, 4))  # Thanksgiving: 4th Thu Nov

    # Good Friday: two days before Easter Sunday
    holidays.add(_easter_sunday(year) - timedelta(days=2))

    return frozenset(holidays)


def is_trading_day(day: date) -> bool:
    """Return True if ``day`` is a US equity market trading day.

    A trading day is any weekday (Mon-Fri) that is not a full-closure NYSE
    holiday. Early-close days still count as trading days.
    """
    if day.weekday() >= 5:  # Saturday=5, Sunday=6
        return False
    return day not in market_holidays(day.year)


def is_market_open_today(now: datetime | None = None) -> bool:
    """Return True if the US market is open on the current Eastern-Time date.

    ET is the reference clock (same rationale as the digest's ET-anchored
    idempotency key): "today" must mean the trading day the digest summarizes,
    not a UTC calendar date that can straddle two ET days.

    ``now`` is injectable for deterministic testing.
    """
    reference = now.astimezone(_ET_ZONE) if now is not None else datetime.now(_ET_ZONE)
    return is_trading_day(reference.date())
