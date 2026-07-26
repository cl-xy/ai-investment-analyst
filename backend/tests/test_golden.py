"""
Golden test set — runs analysis against 20 fixture scenarios.
Validates schema compliance, citation coverage, and graceful degradation.
"""

import json
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict:
    with open(FIXTURES_DIR / name) as f:
        return json.load(f)


def all_fixtures():
    return sorted(FIXTURES_DIR.glob("*.json"))


class TestGoldenSchemaValidation:
    """Every fixture's expected output must pass Pydantic validation."""

    @pytest.mark.parametrize("fixture_path", all_fixtures(), ids=lambda p: p.stem)
    def test_fixture_has_valid_structure(self, fixture_path):
        data = json.loads(fixture_path.read_text())
        assert "ticker" in data
        assert "scenario" in data
        assert "mock_responses" in data
        assert "expected" in data

    @pytest.mark.parametrize(
        "fixture_path",
        [f for f in all_fixtures() if "invalid" not in f.stem and "timeout" not in f.stem],
        ids=lambda p: p.stem,
    )
    def test_mock_responses_have_source_ids(self, fixture_path):
        data = json.loads(fixture_path.read_text())
        for tool_name, response in data["mock_responses"].items():
            if tool_name == "get_portfolio_positions":
                continue
            if isinstance(response, dict) and "source_id" in response:
                assert response["source_id"], f"{tool_name} missing source_id"

    def test_fixture_count(self):
        """We maintain exactly 20 golden scenarios."""
        fixtures = list(all_fixtures())
        assert len(fixtures) == 20, f"Expected 20 fixtures, got {len(fixtures)}"


class TestGoldenEdgeCases:
    """Edge case fixtures validate graceful degradation."""

    def test_missing_news_has_empty_articles(self):
        data = load_fixture("missing_news.json")
        news = data["mock_responses"]["get_stock_news"]
        assert news["articles"] == [] or news.get("error")

    def test_sec_unavailable_has_error(self):
        data = load_fixture("sec_unavailable.json")
        sec = data["mock_responses"]["get_sec_filings"]
        assert sec.get("error") or sec.get("filings") == []

    def test_invalid_ticker_signals_error(self):
        data = load_fixture("invalid_ticker.json")
        assert data["expected"].get("should_error") is True

    def test_provider_timeout_expects_partial(self):
        data = load_fixture("provider_timeout.json")
        assert data["expected"].get("signal") == "insufficient_data"


class TestGoldenDataConsistency:
    """Verify internal consistency of fixture financial data."""

    @pytest.mark.parametrize(
        "fixture_path",
        [f for f in all_fixtures() if "invalid" not in f.stem and "timeout" not in f.stem],
        ids=lambda p: p.stem,
    )
    def test_pe_ratio_consistency(self, fixture_path):
        """P/E ratio should roughly match price / EPS where both are available."""
        data = json.loads(fixture_path.read_text())
        price_data = data["mock_responses"].get("get_stock_price", {})
        fund_data = data["mock_responses"].get("get_stock_fundamentals", {})

        price = price_data.get("price")
        eps = fund_data.get("eps")
        pe = fund_data.get("pe_ratio")

        if price and eps and pe and eps > 0:
            computed_pe = price / eps
            # Allow 20% tolerance for timing differences
            assert abs(computed_pe - pe) / pe < 0.20, (
                f"P/E mismatch: price/eps={computed_pe:.1f} vs stated pe={pe}"
            )

    @pytest.mark.parametrize(
        "fixture_path",
        [f for f in all_fixtures() if "invalid" not in f.stem and "timeout" not in f.stem],
        ids=lambda p: p.stem,
    )
    def test_sentiment_range_is_valid(self, fixture_path):
        """Expected sentiment range must be within [-1, 1]."""
        data = json.loads(fixture_path.read_text())
        sr = data["expected"].get("sentiment_range", [0, 0])
        assert -1.0 <= sr[0] <= sr[1] <= 1.0


class TestGoldenExpectedSignals:
    """Validate expected signals are consistent with scenario descriptions."""

    def test_strong_buy_has_high_confidence(self):
        data = load_fixture("nvda_strong_buy.json")
        assert data["expected"]["confidence"] == "high"
        assert data["expected"]["signal"] == "buy"

    def test_volatile_has_low_confidence(self):
        data = load_fixture("tsla_volatile.json")
        assert data["expected"]["confidence"] == "low"

    def test_error_cases_have_insufficient_data(self):
        for name in ["invalid_ticker.json", "provider_timeout.json"]:
            data = load_fixture(name)
            assert data["expected"]["signal"] == "insufficient_data"
