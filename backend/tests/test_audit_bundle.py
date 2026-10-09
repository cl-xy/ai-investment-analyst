"""
Regression tests for get_audit_bundle.

The ticker_analyses table has no run_id/citations/data_gaps columns and no
direct FK to runs; the only real link is predictions.correlation_id (== the
run_id used by the audit route and evidence_artifacts) -> analysis_id ->
ticker_analyses.analysis_id. The audit bundle must build successfully (its
primary value is evidence_artifacts + citation_validations, both correctly
keyed by run_id) and degrade the secondary analyses section gracefully rather
than failing the whole bundle.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from src.evidence.registry import get_audit_bundle


def _run_row() -> dict:
    now = datetime.now(timezone.utc)
    return {
        "started_at": now,
        "completed_at": now,
        "duration_ms": 1234,
        "router_model": "r",
        "analysis_model": "a",
        "total_tokens": 100,
    }


@pytest.mark.asyncio
async def test_audit_bundle_builds_with_analyses_via_prediction_join():
    analysis_rows = [
        {
            "ticker": "NVDA",
            "signal": "buy",
            "confidence": "high",
            "thesis": "strong",
            "bull_case": '["up"]',
            "bear_case": '["down"]',
            "risk_flags": '["r1"]',
        }
    ]

    with (
        patch(
            "src.evidence.registry.fetchrow",
            new_callable=AsyncMock,
            side_effect=[_run_row(), None],  # run_row, then citation_validations None
        ),
        patch(
            "src.evidence.registry.fetch",
            new_callable=AsyncMock,
            side_effect=[[], analysis_rows],  # artifacts empty, then analyses
        ),
    ):
        bundle = await get_audit_bundle("run-123")

    assert bundle is not None
    assert bundle["run_id"] == "run-123"
    assert bundle["analyses_status"] == "ok"
    assert bundle["analyses"][0]["ticker"] == "NVDA"
    assert bundle["analyses"][0]["bull_case"] == ["up"]
    assert bundle["analyses"][0]["risk_flags"] == ["r1"]
    # Integrity hash is always computed.
    assert bundle["integrity"]["bundle_hash"]


@pytest.mark.asyncio
async def test_audit_bundle_degrades_when_analyses_query_fails():
    def _fetch_side_effect(sql, *args):
        if "FROM evidence_artifacts" in sql:
            return []
        raise RuntimeError("undefined column / query failed")

    with (
        patch(
            "src.evidence.registry.fetchrow",
            new_callable=AsyncMock,
            side_effect=[_run_row(), None],
        ),
        patch("src.evidence.registry.fetch", new_callable=AsyncMock) as mock_fetch,
    ):
        mock_fetch.side_effect = _fetch_side_effect
        bundle = await get_audit_bundle("run-456")

    assert bundle is not None
    assert bundle["analyses"] == []
    assert bundle["analyses_status"] == "unavailable_query_failed"
    assert bundle["integrity"]["bundle_hash"]


@pytest.mark.asyncio
async def test_audit_bundle_none_for_unknown_run():
    with patch("src.evidence.registry.fetchrow", new_callable=AsyncMock, return_value=None):
        bundle = await get_audit_bundle("missing")
    assert bundle is None


@pytest.mark.asyncio
async def test_audit_bundle_empty_analyses_when_no_linkage():
    with (
        patch(
            "src.evidence.registry.fetchrow",
            new_callable=AsyncMock,
            side_effect=[_run_row(), None],
        ),
        patch(
            "src.evidence.registry.fetch",
            new_callable=AsyncMock,
            side_effect=[[], []],  # no artifacts, no linked analyses
        ),
    ):
        bundle = await get_audit_bundle("run-789")

    assert bundle is not None
    assert bundle["analyses"] == []
    assert bundle["analyses_status"] == "unavailable_no_linkage"
