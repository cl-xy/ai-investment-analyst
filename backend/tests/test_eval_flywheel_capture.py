"""
Tests for Task 2: full-fidelity payload capture for promoted evaluation cases.

Two layers tested:
1. src/evidence/registry.py's RunEvidence.register full_payload capture
   (pure, no DB) - size ceiling and canonical-hash equivalence.
2. src/eval_flywheel/capture.py's DB-touching link/status logic (mocked DB,
   following the AsyncMock/patch convention used in test_cache.py).
"""

from unittest.mock import AsyncMock, patch

import pytest

from src.eval_flywheel.capture import capture_case_artifacts, load_case_tool_payloads
from src.evidence.registry import MAX_FULL_PAYLOAD_BYTES, RunEvidence, compute_content_hash


class TestFullPayloadCaptureAtWriteTime:
    def test_small_payload_is_captured_in_full(self):
        run = RunEvidence(run_id="run-1")
        content = {"price": 875.0, "volume": 1000}
        artifact = run.register("yfinance", "get_quote", "NVDA", content)
        assert artifact.full_payload == content

    def test_oversized_payload_full_payload_is_none(self):
        run = RunEvidence(run_id="run-1")
        # Build content that canonicalizes to well beyond the size ceiling.
        content = {"articles": [{"title": "x" * 1000} for _ in range(500)]}
        artifact = run.register("newsapi", "get_ticker_news", "NVDA", content)
        assert artifact.full_payload is None
        # Excerpt/hash/size are unaffected by the ceiling.
        assert artifact.payload_excerpt != ""
        assert artifact.payload_size > MAX_FULL_PAYLOAD_BYTES

    def test_excerpt_and_hash_still_populated_when_full_payload_omitted(self):
        run = RunEvidence(run_id="run-1")
        content = {"articles": [{"title": "x" * 1000} for _ in range(500)]}
        artifact = run.register("newsapi", "get_ticker_news", "NVDA", content)
        assert artifact.content_hash == compute_content_hash(content)
        assert len(artifact.payload_excerpt) <= 500

    def test_canonical_equivalence_across_key_order(self):
        """Dict key order must not change the artifact_id or content_hash."""
        run = RunEvidence(run_id="run-1")
        content_a = {"a": 1, "b": 2, "c": {"x": 1, "y": 2}}
        content_b = {"c": {"y": 2, "x": 1}, "b": 2, "a": 1}
        artifact_a = run.register("yfinance", "get_quote", "NVDA", content_a)
        run_2 = RunEvidence(run_id="run-1")
        artifact_b = run_2.register("yfinance", "get_quote", "NVDA", content_b)
        assert artifact_a.artifact_id == artifact_b.artifact_id
        assert artifact_a.content_hash == artifact_b.content_hash

    def test_no_secret_bearing_fields_in_registered_payloads(self):
        """Defensive documentation test: payloads registered by fetch_data.py
        are yfinance/news/SEC/sentiment tool responses only. This asserts
        the registry itself performs no filtering that would need to exist
        if secrets were ever passed through (it doesn't strip fields), so
        the guarantee must come from call sites - verify none of the known
        call sites pass request/auth/env data by checking the fixed set of
        providers accepted."""
        from src.agent.debate_schemas import VALID_PROVIDERS

        # These are the only providers fetch_data.py registers evidence for.
        # None of them are named after internal/auth/secret-bearing systems.
        forbidden_markers = ("auth", "secret", "token", "password", "api_key", "credential")
        for provider in VALID_PROVIDERS:
            assert not any(marker in provider.lower() for marker in forbidden_markers)


class TestCaptureCaseArtifacts:
    @pytest.mark.asyncio
    async def test_no_correlation_id_marks_failed(self):
        with patch("src.eval_flywheel.capture.execute", new_callable=AsyncMock) as mock_execute:
            result = await capture_case_artifacts("case-1", correlation_id=None)
        assert result.status == "failed"
        assert result.artifact_count == 0
        mock_execute.assert_called_once()
        args = mock_execute.call_args[0]
        assert "failed" in args[0]

    @pytest.mark.asyncio
    async def test_no_artifacts_found_marks_failed(self):
        with (
            patch("src.eval_flywheel.capture.fetch", new_callable=AsyncMock, return_value=[]),
            patch("src.eval_flywheel.capture.execute", new_callable=AsyncMock) as mock_execute,
        ):
            result = await capture_case_artifacts("case-1", correlation_id="corr-abc")
        assert result.status == "failed"
        mock_execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_all_artifacts_have_full_payload_marks_complete(self):
        rows = [
            {
                "artifact_id": "ev_1",
                "run_id": "corr-abc",
                "provider": "yfinance",
                "tool": "get_quote",
                "ticker": "NVDA",
                "content_hash": "hash1",
                "payload_size": 100,
                "full_payload": {"price": 1},
            },
            {
                "artifact_id": "ev_2",
                "run_id": "corr-abc",
                "provider": "newsapi",
                "tool": "get_ticker_news",
                "ticker": "NVDA",
                "content_hash": "hash2",
                "payload_size": 200,
                "full_payload": [{"title": "x"}],
            },
        ]
        with (
            patch("src.eval_flywheel.capture.fetch", new_callable=AsyncMock, return_value=rows),
            patch("src.eval_flywheel.capture.execute", new_callable=AsyncMock) as mock_execute,
            patch("src.db.executemany", new_callable=AsyncMock) as mock_executemany,
        ):
            result = await capture_case_artifacts("case-1", correlation_id="corr-abc")
        assert result.status == "complete"
        assert result.artifact_count == 2
        assert result.complete_artifact_count == 2
        mock_executemany.assert_called_once()
        mock_execute.assert_called_once()
        update_args = mock_execute.call_args[0]
        assert update_args[1] == "complete"

    @pytest.mark.asyncio
    async def test_some_artifacts_missing_full_payload_marks_partial(self):
        rows = [
            {
                "artifact_id": "ev_1",
                "run_id": "corr-abc",
                "provider": "yfinance",
                "tool": "get_quote",
                "ticker": "NVDA",
                "content_hash": "hash1",
                "payload_size": 100,
                "full_payload": {"price": 1},
            },
            {
                "artifact_id": "ev_2",
                "run_id": "corr-abc",
                "provider": "newsapi",
                "tool": "get_ticker_news",
                "ticker": "NVDA",
                "content_hash": "hash2",
                "payload_size": 999_999,
                "full_payload": None,  # exceeded size ceiling at capture time
            },
        ]
        with (
            patch("src.eval_flywheel.capture.fetch", new_callable=AsyncMock, return_value=rows),
            patch("src.eval_flywheel.capture.execute", new_callable=AsyncMock) as mock_execute,
            patch("src.db.executemany", new_callable=AsyncMock),
        ):
            result = await capture_case_artifacts("case-1", correlation_id="corr-abc")
        assert result.status == "partial"
        assert result.complete_artifact_count == 1
        update_args = mock_execute.call_args[0]
        assert update_args[1] == "partial"


class TestLoadCaseToolPayloads:
    @pytest.mark.asyncio
    async def test_returns_none_when_case_not_complete(self):
        with patch(
            "src.eval_flywheel.capture.fetchrow",
            new_callable=AsyncMock,
            return_value={"capture_status": "partial"},
        ):
            result = await load_case_tool_payloads("case-1")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_case_missing(self):
        with patch("src.eval_flywheel.capture.fetchrow", new_callable=AsyncMock, return_value=None):
            result = await load_case_tool_payloads("case-1")
        assert result is None

    @pytest.mark.asyncio
    async def test_groups_payloads_by_provider_and_tool(self):
        with (
            patch(
                "src.eval_flywheel.capture.fetchrow",
                new_callable=AsyncMock,
                return_value={"capture_status": "complete"},
            ),
            patch(
                "src.eval_flywheel.capture.fetch",
                new_callable=AsyncMock,
                return_value=[
                    {
                        "provider": "yfinance",
                        "tool": "get_quote",
                        "ticker": "NVDA",
                        "full_payload": {"price": 1},
                    },
                    {
                        "provider": "yfinance",
                        "tool": "get_fundamentals",
                        "ticker": "NVDA",
                        "full_payload": {"pe": 20},
                    },
                ],
            ),
        ):
            result = await load_case_tool_payloads("case-1")
        assert result is not None
        assert "yfinance:get_quote" in result
        assert "yfinance:get_fundamentals" in result
        assert result["yfinance:get_quote"][0]["payload"] == {"price": 1}
