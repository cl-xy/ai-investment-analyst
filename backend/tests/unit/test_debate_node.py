"""Unit tests for debate node prompt context assembly."""

from src.agent.nodes.debate import _build_data_context


def _state(raw_earnings=None, raw_prices=None):
    return {
        "raw_prices": raw_prices or {},
        "raw_news": {},
        "raw_filings": {},
        "raw_earnings": raw_earnings or {},
    }


def test_build_data_context_includes_earnings_when_present():
    state = _state(raw_earnings={"NVDA": {"next_earnings_date": "2026-08-15", "days_until_earnings": 17}})
    ctx = _build_data_context("NVDA", state)

    assert "2026-08-15" in ctx["earnings"]
    assert "earnings_source_id" in ctx
    assert ctx["raw_earnings"] == {"next_earnings_date": "2026-08-15", "days_until_earnings": 17}


def test_build_data_context_defaults_when_no_earnings_data():
    state = _state()
    ctx = _build_data_context("NVDA", state)

    assert ctx["earnings"] == "No confirmed upcoming earnings date."
    assert ctx["raw_earnings"] == {}


def test_build_data_context_earnings_excluded_from_prompt_format_kwargs():
    """raw_earnings/raw_price_data are internal-only and must not leak into
    str.format() calls against the human prompt templates (they're plain
    dicts, not template placeholders)."""
    from src.agent.prompts.debate_prompts import BULL_HUMAN

    state = _state(raw_earnings={"NVDA": {"next_earnings_date": "2026-08-15"}})
    ctx = _build_data_context("NVDA", state)

    filtered = {k: v for k, v in ctx.items() if k not in ("raw_price_data", "raw_earnings")}
    prompt = BULL_HUMAN.format(**filtered)
    assert "2026-08-15" in prompt
