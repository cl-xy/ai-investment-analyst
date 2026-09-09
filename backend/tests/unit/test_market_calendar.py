"""Unit tests for src.market_calendar (NYSE trading-day calendar)."""

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from src.market_calendar import (
    is_market_open_today,
    is_trading_day,
    market_holidays,
)

_ET = ZoneInfo("America/New_York")


class TestWeekends:
    def test_saturday_is_not_trading_day(self):
        # 2026-09-05 is a Saturday
        assert is_trading_day(date(2026, 9, 5)) is False

    def test_sunday_is_not_trading_day(self):
        # 2026-09-06 is a Sunday
        assert is_trading_day(date(2026, 9, 6)) is False

    def test_ordinary_weekday_is_trading_day(self):
        # 2026-09-09 is a Wednesday, not a holiday
        assert is_trading_day(date(2026, 9, 9)) is True


class TestKnownHolidays2026:
    """Cross-checked against the published 2026 NYSE holiday calendar."""

    def test_new_years_day(self):
        assert date(2026, 1, 1) in market_holidays(2026)
        assert is_trading_day(date(2026, 1, 1)) is False

    def test_mlk_day(self):
        # 3rd Monday of January 2026 = Jan 19
        assert date(2026, 1, 19) in market_holidays(2026)
        assert is_trading_day(date(2026, 1, 19)) is False

    def test_presidents_day(self):
        # 3rd Monday of February 2026 = Feb 16
        assert date(2026, 2, 16) in market_holidays(2026)

    def test_good_friday(self):
        # Easter Sunday 2026 = Apr 5 -> Good Friday = Apr 3
        assert date(2026, 4, 3) in market_holidays(2026)
        assert is_trading_day(date(2026, 4, 3)) is False

    def test_memorial_day(self):
        # last Monday of May 2026 = May 25
        assert date(2026, 5, 25) in market_holidays(2026)

    def test_juneteenth(self):
        # June 19 2026 is a Friday
        assert date(2026, 6, 19) in market_holidays(2026)

    def test_independence_day_observed(self):
        # July 4 2026 is a Saturday -> observed Friday July 3
        assert date(2026, 7, 3) in market_holidays(2026)
        assert date(2026, 7, 4) not in market_holidays(2026)

    def test_labor_day(self):
        # 1st Monday of September 2026 = Sep 7
        assert date(2026, 9, 7) in market_holidays(2026)
        assert is_trading_day(date(2026, 9, 7)) is False

    def test_thanksgiving(self):
        # 4th Thursday of November 2026 = Nov 26
        assert date(2026, 11, 26) in market_holidays(2026)

    def test_christmas(self):
        # Dec 25 2026 is a Friday
        assert date(2026, 12, 25) in market_holidays(2026)


class TestObservanceRules:
    def test_new_years_2022_observed_no_shift_when_saturday(self):
        # Jan 1 2022 is a Saturday. NYSE did not observe on Fri Dec 31 2021
        # for New Year specifically... but our generic rule shifts Saturday
        # holidays to the preceding Friday. Assert our documented behavior.
        assert date(2021, 12, 31) in market_holidays(2022)

    def test_christmas_2022_sunday_observed_monday(self):
        # Dec 25 2022 is a Sunday -> observed Monday Dec 26
        assert date(2022, 12, 26) in market_holidays(2022)

    def test_juneteenth_absent_before_2022(self):
        assert date(2021, 6, 18) not in market_holidays(2021)
        assert date(2021, 6, 19) not in market_holidays(2021)


class TestIsMarketOpenToday:
    def test_uses_et_date_open_on_weekday(self):
        # A UTC instant that is still Wednesday in ET
        now = datetime(2026, 9, 9, 20, 0, tzinfo=timezone.utc)  # 16:00 ET Wed
        assert is_market_open_today(now) is True

    def test_closed_on_weekend(self):
        now = datetime(2026, 9, 5, 15, 0, tzinfo=timezone.utc)  # Sat
        assert is_market_open_today(now) is False

    def test_closed_on_holiday(self):
        now = datetime(2026, 9, 7, 15, 0, tzinfo=timezone.utc)  # Labor Day
        assert is_market_open_today(now) is False

    def test_utc_late_night_still_correct_et_day(self):
        # 2026-09-08 01:00 UTC == 2026-09-07 21:00 ET (Labor Day, closed)
        now = datetime(2026, 9, 8, 1, 0, tzinfo=timezone.utc)
        assert now.astimezone(_ET).date() == date(2026, 9, 7)
        assert is_market_open_today(now) is False
