"""Unit tests for debate node prompt context assembly."""

from src.agent.nodes.debate import _build_data_context, _format_sentiment


def _state(raw_earnings=None, raw_prices=None, raw_sentiment=None):
    return {
        "raw_prices": raw_prices or {},
        "raw_news": {},
        "raw_filings": {},
        "raw_earnings": raw_earnings or {},
        "raw_sentiment": raw_sentiment or {},
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

    filtered = {
        k: v for k, v in ctx.items() if k not in ("raw_price_data", "raw_earnings", "raw_sentiment")
    }
    prompt = BULL_HUMAN.format(**filtered)
    assert "2026-08-15" in prompt


def test_build_data_context_includes_sentiment_when_present():
    state = _state(raw_sentiment={"NVDA": {"message_count": 10, "bullish_count": 8, "bearish_count": 2}})
    ctx = _build_data_context("NVDA", state)

    assert "Messages analyzed: 10" in ctx["sentiment_text"]
    assert "sentiment_source_id" in ctx
    assert ctx["raw_sentiment"]["bullish_count"] == 8


def test_build_data_context_defaults_when_no_sentiment_data():
    state = _state()
    ctx = _build_data_context("NVDA", state)

    assert ctx["sentiment_text"] == "No StockTwits sentiment data available."


def test_format_sentiment_includes_ratio_and_samples():
    text = _format_sentiment(
        {
            "message_count": 12,
            "bullish_count": 9,
            "bearish_count": 3,
            "unlabeled_count": 0,
            "bullish_ratio": 0.75,
            "sample_messages": ["To the moon", "Buying more here"],
        }
    )
    assert "Bullish ratio (of labeled messages): 0.75" in text
    assert "To the moon" in text


def test_sentiment_block_appears_in_bull_prompt():
    """The RETAIL SENTIMENT block must actually reach the bull/bear/moderator
    prompts, not just live in the context dict."""
    from src.agent.prompts.debate_prompts import BULL_HUMAN

    state = _state(
        raw_sentiment={"NVDA": {"message_count": 4, "bullish_count": 4, "bearish_count": 0}}
    )
    ctx = _build_data_context("NVDA", state)
    filtered = {
        k: v for k, v in ctx.items() if k not in ("raw_price_data", "raw_earnings", "raw_sentiment")
    }
    prompt = BULL_HUMAN.format(**filtered)

    assert "RETAIL SENTIMENT" in prompt
    assert "Messages analyzed: 4" in prompt
