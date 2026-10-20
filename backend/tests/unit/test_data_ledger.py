"""Tests for the data availability ledger and the banner it feeds."""

from src.agent import data_ledger as ledger
from src.agent.nodes.debate import _merge_gaps


def _all(status=ledger.OK, **overrides):
    out = {tool: ledger.make_status(status) for tool in ledger.SOURCES}
    out.update(overrides)
    return out


def test_classify_failure_buckets():
    assert (
        ledger.classify_failure("Tool get_quote failed: Too Many Requests") == ledger.RATE_LIMITED
    )
    assert ledger.classify_failure("HTTP 429 from provider") == ledger.RATE_LIMITED
    assert ledger.classify_failure("403 Forbidden cf-mitigated: challenge") == ledger.BLOCKED
    assert ledger.classify_failure("Timeout after 30s") == ledger.TIMEOUT
    assert ledger.classify_failure("Budget exhausted for stocktwits") == ledger.BUDGET
    assert ledger.classify_failure("Tool returned empty data for k") == ledger.EMPTY
    assert ledger.classify_failure("something odd") == ledger.ERROR


def test_no_gap_lines_when_everything_returned_data():
    assert ledger.gap_lines(_all()) == []
    assert ledger.gap_lines(_all(ledger.CACHED)) == []


def test_failed_essential_sources_are_listed_with_reason():
    statuses = _all(
        get_fundamentals=ledger.make_status(ledger.RATE_LIMITED),
        get_technical_indicators=ledger.make_status(ledger.EMPTY),
    )
    lines = ledger.gap_lines(statuses)
    assert lines == [
        "Fundamentals: provider rate limited the request",
        "Technical indicators: no data returned",
    ]


def test_optional_sources_do_not_trigger_the_banner():
    statuses = _all(
        get_ticker_sentiment=ledger.make_status(ledger.BLOCKED),
        get_earnings_calendar=ledger.make_status(ledger.EMPTY),
    )
    assert ledger.gap_lines(statuses) == []


def test_stale_data_is_disclosed_with_age():
    statuses = _all(get_quote=ledger.make_status(ledger.STALE, age_seconds=3 * 3600))
    assert ledger.gap_lines(statuses) == [
        "Price quote: showing cached data 3h old (provider unavailable)"
    ]


def test_failure_gap_texts_skip_empty_earnings_but_keep_sentiment():
    statuses = _all(
        get_earnings_calendar=ledger.make_status(ledger.EMPTY),
        get_ticker_sentiment=ledger.make_status(ledger.BLOCKED),
    )
    texts = ledger.failure_gap_texts("NVDA", statuses)
    assert texts == ["Retail sentiment unavailable for NVDA"]


def test_prompt_block_marks_unavailable_and_stale():
    statuses = _all(
        get_fundamentals=ledger.make_status(ledger.BLOCKED),
        get_quote=ledger.make_status(ledger.STALE, age_seconds=7200),
    )
    block = ledger.format_for_prompt(statuses)
    assert "Fundamentals: UNAVAILABLE" in block
    assert "Price quote: available but stale (2h old)" in block
    assert "News: available" in block


def test_moderator_gaps_cannot_contradict_the_ledger():
    # Ledger says everything is fine; the moderator invents missing data.
    invented = [
        "Complete absence of fundamentals (revenue, earnings, margins)",
        "No technical indicators (RSI, MACD, moving averages)",
        "No SEC financial filings (10-Q, 10-K) provided",
        "No retail sentiment data available",
    ]
    assert _merge_gaps(_all(), invented) == []


def test_moderator_gaps_about_other_things_are_kept():
    extra = "Only two analyst estimates available; consensus is thin"
    lines = _merge_gaps(_all(get_fundamentals=ledger.make_status(ledger.BLOCKED)), [extra])
    assert lines[0] == "Fundamentals: provider blocked the request"
    assert extra in lines
