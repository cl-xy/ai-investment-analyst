"""
Tests for Task 3: wiring promotion into the prediction-resolution flow.

Two layers:
1. src/eval_flywheel/promotion.py in isolation (mocked DB) - first-time
   promotion, idempotent repeat, exclusion recording, race-lost handling,
   and failure isolation within a batch.
2. calibration.py's resolve_predictions() - verifies a promotion-batch
   failure never affects the resolved_count / prediction resolution
   contract that existed before this feature.
"""

from unittest.mock import AsyncMock, patch

import pytest
from src.eval_flywheel.promotion import (
    promote_resolved_prediction,
    promote_resolved_predictions_batch,
)


def _row(**overrides) -> dict:
    defaults = dict(
        id="pred-1",
        analysis_id="analysis-1",
        ticker="NVDA",
        signal="buy",
        confidence="high",
        outcome="incorrect",
        realized_return=-0.05,
        excess_return=-0.09,
        correlation_id="corr-1",
    )
    defaults.update(overrides)
    return defaults


class TestPromoteResolvedPredictionFirstTime:
    @pytest.mark.asyncio
    async def test_promotes_when_material(self):
        with (
            patch(
                "src.eval_flywheel.promotion.fetchrow",
                new_callable=AsyncMock,
                side_effect=[None, {"id": "case-1"}],  # not-yet-classified, then insert result
            ),
            patch(
                "src.eval_flywheel.promotion.build_facts_for_prediction",
                new_callable=AsyncMock,
            ) as mock_facts,
            patch(
                "src.eval_flywheel.promotion.capture_case_artifacts",
                new_callable=AsyncMock,
            ) as mock_capture,
        ):
            from src.eval_flywheel.policy import ResolvedPredictionFacts

            mock_facts.return_value = ResolvedPredictionFacts(
                prediction_id="pred-1",
                ticker="NVDA",
                signal="buy",
                confidence="high",
                outcome="incorrect",
                realized_return=-0.05,
                excess_return=-0.09,
                citation_invalid_ratio=None,
                data_gaps_count=0,
            )
            outcome = await promote_resolved_prediction(_row())

        assert outcome == "promoted"
        mock_capture.assert_called_once_with("case-1", "corr-1")

    @pytest.mark.asyncio
    async def test_excludes_when_not_material(self):
        with (
            patch(
                "src.eval_flywheel.promotion.fetchrow",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "src.eval_flywheel.promotion.build_facts_for_prediction",
                new_callable=AsyncMock,
            ) as mock_facts,
            patch("src.eval_flywheel.promotion.execute", new_callable=AsyncMock) as mock_execute,
        ):
            from src.eval_flywheel.policy import ResolvedPredictionFacts

            mock_facts.return_value = ResolvedPredictionFacts(
                prediction_id="pred-1",
                ticker="NVDA",
                signal="buy",
                confidence="medium",
                outcome="correct",
                realized_return=0.01,
                excess_return=0.01,
                citation_invalid_ratio=None,
                data_gaps_count=0,
            )
            outcome = await promote_resolved_prediction(_row(outcome="correct"))

        assert outcome == "excluded"
        mock_execute.assert_called_once()


class TestPromoteResolvedPredictionIdempotency:
    @pytest.mark.asyncio
    async def test_already_classified_short_circuits(self):
        with patch(
            "src.eval_flywheel.promotion.fetchrow",
            new_callable=AsyncMock,
            return_value={"id": "existing-case"},
        ):
            outcome = await promote_resolved_prediction(_row())
        assert outcome == "already_classified"

    @pytest.mark.asyncio
    async def test_lost_race_on_insert_returns_already_classified(self):
        """ON CONFLICT (prediction_id) DO NOTHING with no RETURNING row means
        a concurrent promotion sweep already inserted this case."""
        with (
            patch(
                "src.eval_flywheel.promotion.fetchrow",
                new_callable=AsyncMock,
                side_effect=[None, None],  # not-yet-classified, then insert returns nothing
            ),
            patch(
                "src.eval_flywheel.promotion.build_facts_for_prediction",
                new_callable=AsyncMock,
            ) as mock_facts,
        ):
            from src.eval_flywheel.policy import ResolvedPredictionFacts

            mock_facts.return_value = ResolvedPredictionFacts(
                prediction_id="pred-1",
                ticker="NVDA",
                signal="buy",
                confidence="high",
                outcome="incorrect",
                realized_return=-0.05,
                excess_return=-0.09,
                citation_invalid_ratio=None,
                data_gaps_count=0,
            )
            outcome = await promote_resolved_prediction(_row())
        assert outcome == "already_classified"


class TestPromoteResolvedPredictionCaptureFailureIsolation:
    @pytest.mark.asyncio
    async def test_capture_failure_does_not_raise_or_change_outcome(self):
        with (
            patch(
                "src.eval_flywheel.promotion.fetchrow",
                new_callable=AsyncMock,
                side_effect=[None, {"id": "case-1"}],
            ),
            patch(
                "src.eval_flywheel.promotion.build_facts_for_prediction",
                new_callable=AsyncMock,
            ) as mock_facts,
            patch(
                "src.eval_flywheel.promotion.capture_case_artifacts",
                new_callable=AsyncMock,
                side_effect=RuntimeError("db down"),
            ),
        ):
            from src.eval_flywheel.policy import ResolvedPredictionFacts

            mock_facts.return_value = ResolvedPredictionFacts(
                prediction_id="pred-1",
                ticker="NVDA",
                signal="buy",
                confidence="high",
                outcome="incorrect",
                realized_return=-0.05,
                excess_return=-0.09,
                citation_invalid_ratio=None,
                data_gaps_count=0,
            )
            outcome = await promote_resolved_prediction(_row())
        # Still reports "promoted" - the case exists even though replay
        # capture failed; capture_status reflects the failure separately.
        assert outcome == "promoted"


class TestPromoteResolvedPredictionsBatch:
    @pytest.mark.asyncio
    async def test_one_failure_does_not_abort_batch(self):
        async def _side_effect(row):
            if row["id"] == "bad":
                raise RuntimeError("boom")
            return "promoted"

        with patch(
            "src.eval_flywheel.promotion.promote_resolved_prediction",
            side_effect=_side_effect,
        ):
            summary = await promote_resolved_predictions_batch(
                [_row(id="good-1"), _row(id="bad"), _row(id="good-2")]
            )

        assert summary.considered == 3
        assert summary.promoted == 2
        assert summary.failed == 1

    @pytest.mark.asyncio
    async def test_empty_batch(self):
        summary = await promote_resolved_predictions_batch([])
        assert summary.considered == 0
        assert summary.promoted == 0


class TestResolvePredictionsToleratesPromotionFailure:
    @pytest.mark.asyncio
    async def test_resolution_succeeds_even_if_promotion_batch_raises(self):
        """The pre-existing resolved_count contract must be unaffected by a
        promotion-layer failure. This directly exercises resolve_predictions'
        exception isolation around the flywheel call."""
        from datetime import datetime, timedelta, timezone

        from src.api.routes.calibration import resolve_predictions

        now = datetime.now(timezone.utc)
        old_created_at = now - timedelta(days=31)

        fake_row = {
            "id": "pred-1",
            "analysis_id": "analysis-1",
            "ticker": "NVDA",
            "signal": "buy",
            "confidence": "high",
            "price_at_prediction": 100.0,
            "horizon_days": 30,
            "created_at": old_created_at,
            "correlation_id": "corr-1",
        }

        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[fake_row])
        mock_conn.execute = AsyncMock()
        mock_conn.transaction = _FakeTransactionCtx

        mock_pool = AsyncMock()
        mock_pool.acquire = _make_acquire_ctx(mock_conn)

        with (
            patch("src.db.get_pool", new_callable=AsyncMock, return_value=mock_pool),
            patch("src.api.routes.calibration._fetch_adjusted_price", return_value=110.0),
            patch("src.api.routes.calibration._fetch_benchmark_return", return_value=0.01),
            patch(
                "src.eval_flywheel.promotion.promote_resolved_predictions_batch",
                new_callable=AsyncMock,
                side_effect=RuntimeError("promotion layer down"),
            ),
            patch("src.api.routes.calibration.settings") as mock_settings,
        ):
            mock_settings.scheduler_secret_token = "test-token"  # pragma: allowlist secret
            result = await resolve_predictions(x_scheduler_token="test-token")

        assert result["resolved_count"] == 1
        # Promotion failed entirely, but resolution still reports success and
        # a degraded-but-present promotion summary (all zeros).
        assert result["promotion"] == {
            "promoted": 0,
            "excluded": 0,
            "already_classified": 0,
            "failed": 0,
        }


class _FakeTransactionCtx:
    """Minimal async context manager standing in for conn.transaction()."""

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def _make_acquire_ctx(conn):
    class _AcquireCtx:
        async def __aenter__(self):
            return conn

        async def __aexit__(self, *exc):
            return False

    def _acquire():
        return _AcquireCtx()

    return _acquire
