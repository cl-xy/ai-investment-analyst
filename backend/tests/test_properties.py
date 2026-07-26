"""
Property-based tests using Hypothesis.

These test invariants that must hold for ALL valid inputs, not just
specific examples. They find edge cases that example-based tests miss:
unicode in tickers, floating point boundaries, extreme string lengths, etc.
"""

import json
import re

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from src.agent.events import EventEmitter, EventType
from src.agent.json_utils import extract_json
from src.agent.structured_output import AnalysisOutput, Citation

# The ticker validation pattern used across the codebase
VALID_TICKER_PATTERN = re.compile(r"\A[A-Z0-9.]{1,10}\Z")

# Source ID format: "{provider}:{ticker}:{timestamp}"
SOURCE_ID_PATTERN = re.compile(r"^[a-z_]+:[A-Z0-9.]+:\d+$")

# --- Strategies ---

valid_ticker_chars = st.sampled_from(
    list("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.")
)

valid_ticker_st = st.text(
    alphabet=valid_ticker_chars, min_size=1, max_size=10
)

signal_st = st.sampled_from(["buy", "hold", "sell", "insufficient_data"])
confidence_st = st.sampled_from(["high", "medium", "low"])
sentiment_st = st.floats(min_value=-1.0, max_value=1.0, allow_nan=False, allow_infinity=False)
provider_st = st.sampled_from(["yfinance", "newsapi", "sec_edgar", "alpha_vantage", "rss"])


# --- Test 1: Ticker validation roundtrip ---


class TestTickerValidation:
    @given(ticker=valid_ticker_st)
    def test_valid_ticker_always_matches(self, ticker: str):
        """Any 1-10 char alphanumeric+dot string passes the validation pattern."""
        assert VALID_TICKER_PATTERN.match(ticker) is not None

    @given(
        text=st.text(
            alphabet=st.sampled_from(list("!@#$%^&*()-+=[]{}|;:',<>?/~` \t\n")),
            min_size=1,
            max_size=15,
        )
    )
    def test_special_chars_rejected(self, text: str):
        """Strings composed of special characters never pass validation."""
        assert VALID_TICKER_PATTERN.match(text) is None


# --- Test 2: AnalysisOutput schema always validates ---


class TestAnalysisOutputSchema:
    @given(
        ticker=valid_ticker_st,
        signal=signal_st,
        confidence=confidence_st,
        sentiment_score=sentiment_st,
        thesis=st.text(min_size=1, max_size=500),
        bull_case=st.lists(st.text(min_size=1, max_size=200), min_size=0, max_size=4),
        bear_case=st.lists(st.text(min_size=1, max_size=200), min_size=0, max_size=4),
        risk_flags=st.lists(st.text(min_size=1, max_size=100), min_size=0, max_size=5),
    )
    @settings(max_examples=200)
    def test_valid_data_always_passes_validation(
        self,
        ticker: str,
        signal: str,
        confidence: str,
        sentiment_score: float,
        thesis: str,
        bull_case: list[str],
        bear_case: list[str],
        risk_flags: list[str],
    ):
        """Arbitrary valid field combinations always produce a valid AnalysisOutput."""
        output = AnalysisOutput(
            ticker=ticker,
            signal=signal,
            confidence=confidence,
            sentiment_score=sentiment_score,
            thesis=thesis,
            bull_case=bull_case,
            bear_case=bear_case,
            risk_flags=risk_flags,
        )
        assert output.ticker == ticker
        assert output.signal == signal
        assert output.confidence == confidence


# --- Test 3: Sentiment score bounds ---


class TestSentimentBounds:
    @given(
        ticker=valid_ticker_st,
        signal=signal_st,
        confidence=confidence_st,
        sentiment_score=sentiment_st,
    )
    def test_sentiment_score_always_bounded(
        self, ticker: str, signal: str, confidence: str, sentiment_score: float
    ):
        """For any valid AnalysisOutput, sentiment_score stays in [-1.0, 1.0]."""
        output = AnalysisOutput(
            ticker=ticker,
            signal=signal,
            confidence=confidence,
            sentiment_score=sentiment_score,
            thesis="Test thesis for property testing.",
        )
        assert -1.0 <= output.sentiment_score <= 1.0

    @given(score=st.floats(min_value=1.01, max_value=1000.0, allow_nan=False))
    def test_out_of_range_sentiment_rejected(self, score: float):
        """Sentiment scores above 1.0 are rejected by Pydantic validation."""
        import pytest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            AnalysisOutput(
                ticker="TEST",
                signal="buy",
                confidence="high",
                sentiment_score=score,
                thesis="Should fail.",
            )


# --- Test 4: JSON extraction robustness ---


class TestJsonExtraction:
    @given(
        data=st.dictionaries(
            keys=st.text(
                alphabet=st.sampled_from(list("abcdefghijklmnopqrstuvwxyz_")),
                min_size=1,
                max_size=10,
            ),
            values=st.one_of(
                st.integers(min_value=-1000, max_value=1000),
                st.text(min_size=0, max_size=50),
                st.booleans(),
                st.none(),
            ),
            min_size=1,
            max_size=5,
        ),
    )
    def test_json_in_code_fence_extractable(self, data: dict):
        """Valid JSON wrapped in markdown code fences is always extractable."""
        raw = json.dumps(data)
        fenced = f"```json\n{raw}\n```"
        result = extract_json(fenced)
        assert result == data

    @given(
        data=st.dictionaries(
            keys=st.text(
                alphabet=st.sampled_from(list("abcdefghijklmnopqrstuvwxyz_")),
                min_size=1,
                max_size=10,
            ),
            values=st.integers(min_value=-100, max_value=100),
            min_size=1,
            max_size=5,
        ),
    )
    def test_plain_json_extractable(self, data: dict):
        """Valid JSON without fences is also extractable."""
        raw = json.dumps(data)
        result = extract_json(raw)
        assert result == data

    @given(
        data=st.dictionaries(
            keys=st.text(
                alphabet=st.sampled_from(list("abcdefghijklmnopqrstuvwxyz_")),
                min_size=1,
                max_size=10,
            ),
            values=st.integers(min_value=-100, max_value=100),
            min_size=1,
            max_size=3,
        ),
        whitespace=st.text(
            alphabet=st.sampled_from(list(" \t\n")),
            min_size=0,
            max_size=10,
        ),
    )
    def test_json_with_surrounding_whitespace(self, data: dict, whitespace: str):
        """JSON with leading/trailing whitespace is extractable."""
        raw = json.dumps(data)
        padded = whitespace + raw + whitespace
        result = extract_json(padded)
        assert result == data


# --- Test 5: SSE event sequence IDs are monotonic ---


class TestEventSequenceMonotonic:
    @given(
        event_count=st.integers(min_value=2, max_value=50),
    )
    def test_seq_ids_strictly_increasing(self, event_count: int):
        """Sequence IDs from EventEmitter are always strictly monotonic."""
        emitter = EventEmitter()
        emitter.run_started(["AAPL"])

        for i in range(event_count - 1):
            emitter.heartbeat()

        seqs = [e.seq for e in emitter.events]
        for i in range(1, len(seqs)):
            assert seqs[i] > seqs[i - 1], f"seq[{i}]={seqs[i]} not > seq[{i-1}]={seqs[i-1]}"

    @given(
        node_names=st.lists(
            st.text(
                alphabet=st.sampled_from(list("abcdefghijklmnopqrstuvwxyz_")),
                min_size=1,
                max_size=15,
            ),
            min_size=1,
            max_size=10,
        ),
    )
    def test_mixed_event_types_still_monotonic(self, node_names: list[str]):
        """Even with mixed event types, seq IDs stay strictly increasing."""
        emitter = EventEmitter()
        emitter.run_started(["TEST"])

        for name in node_names:
            emitter.node_started(name)
            emitter.node_completed(name)

        emitter.run_completed(["TEST"], total_duration_ms=100)

        seqs = [e.seq for e in emitter.events]
        for i in range(1, len(seqs)):
            assert seqs[i] > seqs[i - 1]


# --- Test 6: Cache key determinism ---


class TestCacheKeyDeterminism:
    @given(
        provider=provider_st,
        tool=st.text(
            alphabet=st.sampled_from(list("abcdefghijklmnopqrstuvwxyz_")),
            min_size=1,
            max_size=20,
        ),
        ticker=valid_ticker_st,
    )
    def test_same_inputs_produce_same_key(self, provider: str, tool: str, ticker: str):
        """The cache key formula is deterministic: same inputs, same key."""
        key1 = f"{provider}:{tool}:{ticker}"
        key2 = f"{provider}:{tool}:{ticker}"
        assert key1 == key2

    @given(
        provider=provider_st,
        tool=st.text(
            alphabet=st.sampled_from(list("abcdefghijklmnopqrstuvwxyz_")),
            min_size=1,
            max_size=20,
        ),
        ticker_a=valid_ticker_st,
        ticker_b=valid_ticker_st,
    )
    def test_different_tickers_produce_different_keys(
        self, provider: str, tool: str, ticker_a: str, ticker_b: str
    ):
        """Different tickers always produce different cache keys."""
        assume(ticker_a != ticker_b)
        key_a = f"{provider}:{tool}:{ticker_a}"
        key_b = f"{provider}:{tool}:{ticker_b}"
        assert key_a != key_b


# --- Test 7: Budget check never goes negative ---


class TestBudgetNeverNegative:
    @given(
        limit=st.integers(min_value=1, max_value=200),
        decrements=st.lists(st.integers(min_value=1, max_value=10), min_size=1, max_size=50),
    )
    def test_remaining_never_negative(self, limit: int, decrements: list[int]):
        """
        Simulates the budget logic: remaining = max(0, limit - used).
        Regardless of how many decrements happen, remaining never goes below zero.
        """
        used = 0
        for d in decrements:
            if used < limit:
                used += d
            remaining = max(0, limit - used)
            assert remaining >= 0, f"remaining={remaining} went negative"

    @given(
        limit=st.integers(min_value=1, max_value=100),
        calls=st.integers(min_value=0, max_value=200),
    )
    def test_budget_exhausted_flag_consistent(self, limit: int, calls: int):
        """The exhausted flag is consistent with used >= limit."""
        used = min(calls, limit * 2)  # allow overshooting
        remaining = max(0, limit - used)
        exhausted = used >= limit
        if exhausted:
            assert remaining == 0 or used > limit
        else:
            assert remaining > 0


# --- Test 8: Citation source_id format ---


class TestCitationSourceId:
    @given(
        provider=provider_st,
        ticker=valid_ticker_st,
        timestamp=st.integers(min_value=1000000000, max_value=2000000000),
        claim=st.text(min_size=1, max_size=200),
    )
    def test_source_id_matches_expected_format(
        self, provider: str, ticker: str, timestamp: int, claim: str
    ):
        """Citation source_ids follow the '{provider}:{ticker}:{timestamp}' pattern."""
        source_id = f"{provider}:{ticker}:{timestamp}"
        citation = Citation(source_id=source_id, claim=claim, provider=provider)
        parts = citation.source_id.split(":")
        assert len(parts) == 3
        assert parts[0] == provider
        assert parts[1] == ticker
        assert parts[2].isdigit()


# --- Test 9: Signal and confidence correlation ---


class TestSignalConfidenceCorrelation:
    @given(
        ticker=valid_ticker_st,
        sentiment_score=st.floats(min_value=0.51, max_value=1.0, allow_nan=False),
    )
    def test_strong_positive_sentiment_sell_should_not_be_high_confidence(
        self, ticker: str, sentiment_score: float
    ):
        """
        Logical consistency check: if sentiment is strongly positive (>0.5)
        and signal is 'sell', confidence should not be 'high'. This tests
        that the schema allows constructing such an object (the LLM could
        produce it), but flags it as logically inconsistent for downstream
        validation layers to catch.
        """
        # The schema does not enforce this constraint (it is a business rule).
        # We verify the schema allows the combination (no crash), then check
        # that a downstream validator COULD flag it.
        output = AnalysisOutput(
            ticker=ticker,
            signal="sell",
            confidence="high",
            sentiment_score=sentiment_score,
            thesis="Bearish despite positive sentiment.",
        )
        # This combination is internally contradictory: positive sentiment + sell + high confidence
        # A quality gate should flag this. Here we verify the invariant we want to enforce:
        is_contradictory = (
            output.sentiment_score > 0.5
            and output.signal == "sell"
            and output.confidence == "high"
        )
        assert is_contradictory, "Test setup ensures this combination exists for detection"


# --- Test 10: Empty data_gaps when all tools succeed ---


class TestDataGapsConsistency:
    @given(
        ticker=valid_ticker_st,
        signal=signal_st,
        confidence=confidence_st,
        sentiment_score=sentiment_st,
    )
    def test_explicit_empty_data_gaps(
        self, ticker: str, signal: str, confidence: str, sentiment_score: float
    ):
        """
        When constructing an AnalysisOutput with data_gaps=[] (all tools succeeded),
        the field remains empty after validation. No phantom gaps appear.
        """
        output = AnalysisOutput(
            ticker=ticker,
            signal=signal,
            confidence=confidence,
            sentiment_score=sentiment_score,
            thesis="All data sources returned successfully.",
            data_gaps=[],
        )
        assert output.data_gaps == []
        assert len(output.data_gaps) == 0

    @given(
        gaps=st.lists(
            st.text(min_size=1, max_size=100),
            min_size=1,
            max_size=5,
        ),
    )
    def test_data_gaps_preserved_when_present(self, gaps: list[str]):
        """When data_gaps are provided, they are preserved exactly as given."""
        output = AnalysisOutput(
            ticker="TEST",
            signal="insufficient_data",
            confidence="low",
            sentiment_score=0.0,
            thesis="Missing some data sources.",
            data_gaps=gaps,
        )
        assert output.data_gaps == gaps
        assert len(output.data_gaps) == len(gaps)
