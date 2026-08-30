"""
Tests for Telegram bot integration.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from src.alerts.composer import Alert
from src.alerts.telegram import (
    _dispatch_allowed,
    _format_alert_message,
    dispatch_alert,
    handle_update,
    register_chat,
    validate_webhook_secret,
)


def _alert(**overrides) -> Alert:
    defaults = dict(
        id="11111111-1111-1111-1111-111111111111",
        ticker="NVDA",
        alert_type="sentiment",
        severity="critical",
        drift_score=0.72,
        old_signal="buy",
        new_signal="hold",
        reasoning_diff={
            "llm_judgment": {
                "changed": True,
                "new_signal": "hold",
                "reasoning": "Sentiment collapsed and a new 8-K raised concerns.",
                "key_shifts": ["sentiment reversal", "new material filing"],
            },
            "triggered_events": [{"type": "sentiment", "summary": "dropped"}],
        },
        triggered_by=["sentiment", "sec_filing"],
        llm_judged=True,
        created_at=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    return Alert(**defaults)


class TestMessageFormatting:
    def test_includes_ticker_and_signal_transition(self):
        message = _format_alert_message(_alert(), "https://example.com")
        assert "NVDA" in message
        assert "BUY" in message
        assert "HOLD" in message

    def test_includes_key_shifts(self):
        message = _format_alert_message(_alert(), "https://example.com")
        assert "sentiment reversal" in message
        assert "new material filing" in message

    def test_includes_deep_link(self):
        message = _format_alert_message(_alert(), "https://example.com")
        assert "https://example.com/analyze?tickers=NVDA" in message

    def test_falls_back_to_triggered_events_without_llm_judgment(self):
        alert = _alert(reasoning_diff={"triggered_events": [{"type": "price", "summary": "moved 8%"}]})
        message = _format_alert_message(alert, "https://example.com")
        assert "moved 8%" in message

    def test_no_signal_change_shows_prior_signal_only(self):
        alert = _alert(new_signal=None)
        message = _format_alert_message(alert, "https://example.com")
        assert "Prior signal" in message


class TestWebhookSecretValidation:
    def test_missing_configured_secret_fails_closed(self):
        with patch("src.config.settings.telegram_webhook_secret", ""):
            assert validate_webhook_secret("anything") is False

    def test_missing_header_rejected(self):
        with patch("src.config.settings.telegram_webhook_secret", "supersecret"):
            assert validate_webhook_secret(None) is False

    def test_wrong_secret_rejected(self):
        with patch("src.config.settings.telegram_webhook_secret", "supersecret"):
            assert validate_webhook_secret("wrong") is False

    def test_correct_secret_accepted(self):
        with patch("src.config.settings.telegram_webhook_secret", "supersecret"):
            assert validate_webhook_secret("supersecret") is True


class TestCommandHandling:
    @pytest.mark.asyncio
    async def test_start_registers_chat_and_sends_welcome(self):
        with (
            patch("src.alerts.telegram.register_chat", new=AsyncMock()) as mock_register,
            patch("src.alerts.telegram.send_test_message", new=AsyncMock()) as mock_send,
        ):
            await handle_update({"message": {"chat": {"id": 123}, "text": "/start"}})

        mock_register.assert_called_once_with(123)
        mock_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_deactivates_chat(self):
        with (
            patch("src.alerts.telegram.deactivate_chat", new=AsyncMock()) as mock_deactivate,
            patch("src.alerts.telegram.send_test_message", new=AsyncMock()),
        ):
            await handle_update({"message": {"chat": {"id": 456}, "text": "/stop"}})

        mock_deactivate.assert_called_once_with(456)

    @pytest.mark.asyncio
    async def test_status_reports_registration_state(self):
        with (
            patch("src.alerts.telegram.is_chat_registered", new=AsyncMock(return_value=True)),
            patch("src.alerts.telegram.send_test_message", new=AsyncMock()) as mock_send,
        ):
            await handle_update({"message": {"chat": {"id": 789}, "text": "/status"}})

        sent_text = mock_send.call_args.args[1]
        assert "subscribed" in sent_text.lower()

    @pytest.mark.asyncio
    async def test_non_command_message_ignored_gracefully(self):
        with patch("src.alerts.telegram.send_test_message", new=AsyncMock()) as mock_send:
            await handle_update({"message": {"chat": {"id": 1}, "text": "hello bot"}})
        mock_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_without_message_is_noop(self):
        # Should not raise
        await handle_update({"callback_query": {}})

    @pytest.mark.asyncio
    async def test_non_integer_chat_id_ignored(self):
        with patch("src.alerts.telegram.register_chat", new=AsyncMock()) as mock_register:
            await handle_update({"message": {"chat": {"id": "not-an-int"}, "text": "/start"}})
        mock_register.assert_not_called()


class TestWatchCommands:
    @pytest.mark.asyncio
    async def test_watch_subscribes_valid_ticker(self):
        from src.alerts.subscriptions import AlertSubscription

        result = AlertSubscription(
            ticker="NVDA", source="telegram", trigger_types=["sec"], active=True
        )
        with (
            patch(
                "src.alerts.subscriptions.subscribe_ticker", new=AsyncMock(return_value=result)
            ) as mock_subscribe,
            patch("src.alerts.telegram.send_test_message", new=AsyncMock()) as mock_send,
        ):
            await handle_update({"message": {"chat": {"id": 1}, "text": "/watch nvda"}})

        mock_subscribe.assert_called_once_with("NVDA", source="telegram")
        sent_text = mock_send.call_args.args[1]
        assert "NVDA" in sent_text

    @pytest.mark.asyncio
    async def test_watch_without_ticker_shows_usage(self):
        with (
            patch("src.alerts.subscriptions.subscribe_ticker", new=AsyncMock()) as mock_subscribe,
            patch("src.alerts.telegram.send_test_message", new=AsyncMock()) as mock_send,
        ):
            await handle_update({"message": {"chat": {"id": 1}, "text": "/watch"}})

        mock_subscribe.assert_not_called()
        assert "usage" in mock_send.call_args.args[1].lower()

    @pytest.mark.asyncio
    async def test_watch_rejects_invalid_ticker(self):
        with (
            patch("src.alerts.subscriptions.subscribe_ticker", new=AsyncMock()) as mock_subscribe,
            patch("src.alerts.telegram.send_test_message", new=AsyncMock()) as mock_send,
        ):
            await handle_update({"message": {"chat": {"id": 1}, "text": "/watch !!!bad!!!"}})

        mock_subscribe.assert_not_called()
        assert "usage" in mock_send.call_args.args[1].lower()

    @pytest.mark.asyncio
    async def test_watch_handles_subscribe_failure_gracefully(self):
        with (
            patch(
                "src.alerts.subscriptions.subscribe_ticker",
                new=AsyncMock(side_effect=RuntimeError("db down")),
            ),
            patch("src.alerts.telegram.send_test_message", new=AsyncMock()) as mock_send,
        ):
            await handle_update({"message": {"chat": {"id": 1}, "text": "/watch NVDA"}})

        assert "couldn't" in mock_send.call_args.args[1].lower()

    @pytest.mark.asyncio
    async def test_unwatch_removes_existing_subscription(self):
        with (
            patch(
                "src.alerts.subscriptions.unsubscribe_ticker", new=AsyncMock(return_value=True)
            ) as mock_unsub,
            patch("src.alerts.telegram.send_test_message", new=AsyncMock()) as mock_send,
        ):
            await handle_update({"message": {"chat": {"id": 1}, "text": "/unwatch NVDA"}})

        mock_unsub.assert_called_once_with("NVDA")
        assert "stopped watching" in mock_send.call_args.args[1].lower()

    @pytest.mark.asyncio
    async def test_unwatch_reports_when_not_subscribed(self):
        with (
            patch(
                "src.alerts.subscriptions.unsubscribe_ticker", new=AsyncMock(return_value=False)
            ),
            patch("src.alerts.telegram.send_test_message", new=AsyncMock()) as mock_send,
        ):
            await handle_update({"message": {"chat": {"id": 1}, "text": "/unwatch NVDA"}})

        assert "wasn't on your watchlist" in mock_send.call_args.args[1]

    @pytest.mark.asyncio
    async def test_watching_lists_all_active_subscriptions(self):
        from src.alerts.subscriptions import AlertSubscription

        subs = [
            AlertSubscription(ticker="NVDA", source="telegram", trigger_types=[], active=True),
            AlertSubscription(ticker="AAPL", source="watchlist", trigger_types=[], active=True),
        ]
        with (
            patch("src.alerts.subscriptions.list_subscriptions", new=AsyncMock(return_value=subs)),
            patch("src.alerts.telegram.send_test_message", new=AsyncMock()) as mock_send,
        ):
            await handle_update({"message": {"chat": {"id": 1}, "text": "/watching"}})

        sent_text = mock_send.call_args.args[1]
        assert "NVDA" in sent_text
        assert "AAPL" in sent_text

    @pytest.mark.asyncio
    async def test_watching_empty_shows_helpful_message(self):
        with (
            patch("src.alerts.subscriptions.list_subscriptions", new=AsyncMock(return_value=[])),
            patch("src.alerts.telegram.send_test_message", new=AsyncMock()) as mock_send,
        ):
            await handle_update({"message": {"chat": {"id": 1}, "text": "/watching"}})

        assert "/watch" in mock_send.call_args.args[1]

    @pytest.mark.asyncio
    async def test_watching_command_not_swallowed_by_watch_prefix(self):
        """Regression guard: '/watching' starts with '/watch' as a string,
        so command dispatch must match on the full token, not a prefix."""
        with (
            patch("src.alerts.subscriptions.list_subscriptions", new=AsyncMock(return_value=[])),
            patch("src.alerts.subscriptions.subscribe_ticker", new=AsyncMock()) as mock_subscribe,
            patch("src.alerts.telegram.send_test_message", new=AsyncMock()),
        ):
            await handle_update({"message": {"chat": {"id": 1}, "text": "/watching"}})

        mock_subscribe.assert_not_called()


class TestDispatchRateLimiting:
    @pytest.mark.asyncio
    async def test_allows_first_dispatch(self):
        with patch("src.alerts.telegram.fetchrow", new=AsyncMock(return_value=None)):
            with patch("src.alerts.telegram.execute", new=AsyncMock()):
                allowed = await _dispatch_allowed("NVDA")
        assert allowed is True

    @pytest.mark.asyncio
    async def test_blocks_dispatch_within_cooldown(self):
        recent = {"last_dispatched_at": datetime.now(timezone.utc) - timedelta(minutes=30)}
        with patch("src.alerts.telegram.fetchrow", new=AsyncMock(return_value=recent)):
            allowed = await _dispatch_allowed("NVDA")
        assert allowed is False

    @pytest.mark.asyncio
    async def test_allows_dispatch_after_cooldown_expires(self):
        old = {"last_dispatched_at": datetime.now(timezone.utc) - timedelta(hours=5)}
        with patch("src.alerts.telegram.fetchrow", new=AsyncMock(return_value=old)):
            with patch("src.alerts.telegram.execute", new=AsyncMock()):
                allowed = await _dispatch_allowed("NVDA")
        assert allowed is True


class TestDispatchAlert:
    @pytest.mark.asyncio
    async def test_dispatch_sends_to_all_active_chats(self):
        with (
            patch("src.alerts.telegram._dispatch_allowed", new=AsyncMock(return_value=True)),
            patch(
                "src.alerts.telegram.get_active_chat_ids",
                new=AsyncMock(return_value=[1, 2, 3]),
            ),
            patch(
                "src.alerts.telegram._call_telegram",
                new=AsyncMock(return_value={"ok": True}),
            ) as mock_call,
            patch("src.alerts.telegram.execute", new=AsyncMock()),
            patch("src.alerts.telegram.mark_alert_dispatched", new=AsyncMock()) as mock_mark,
        ):
            sent = await dispatch_alert(_alert())

        assert sent == 3
        assert mock_call.call_count == 3
        mock_mark.assert_called_once()

    @pytest.mark.asyncio
    async def test_dispatch_skipped_when_cooldown_active(self):
        with (
            patch("src.alerts.telegram._dispatch_allowed", new=AsyncMock(return_value=False)),
            patch(
                "src.alerts.telegram.get_active_chat_ids", new=AsyncMock()
            ) as mock_get_chats,
        ):
            sent = await dispatch_alert(_alert())

        assert sent == 0
        mock_get_chats.assert_not_called()

    @pytest.mark.asyncio
    async def test_dispatch_force_bypasses_cooldown(self):
        with (
            patch(
                "src.alerts.telegram._dispatch_allowed", new=AsyncMock(return_value=False)
            ) as mock_allowed,
            patch(
                "src.alerts.telegram.get_active_chat_ids",
                new=AsyncMock(return_value=[1]),
            ),
            patch(
                "src.alerts.telegram._call_telegram",
                new=AsyncMock(return_value={"ok": True}),
            ),
            patch("src.alerts.telegram.execute", new=AsyncMock()),
            patch("src.alerts.telegram.mark_alert_dispatched", new=AsyncMock()),
        ):
            sent = await dispatch_alert(_alert(), force=True)

        mock_allowed.assert_not_called()
        assert sent == 1

    @pytest.mark.asyncio
    async def test_dispatch_no_subscribers_returns_zero(self):
        with (
            patch("src.alerts.telegram._dispatch_allowed", new=AsyncMock(return_value=True)),
            patch("src.alerts.telegram.get_active_chat_ids", new=AsyncMock(return_value=[])),
        ):
            sent = await dispatch_alert(_alert())
        assert sent == 0

    @pytest.mark.asyncio
    async def test_dispatch_partial_failure_counts_only_successes(self):
        call_results = [{"ok": True}, None, {"ok": False}]

        async def _fake_call(*_args, **_kwargs):
            return call_results.pop(0)

        with (
            patch("src.alerts.telegram._dispatch_allowed", new=AsyncMock(return_value=True)),
            patch(
                "src.alerts.telegram.get_active_chat_ids",
                new=AsyncMock(return_value=[1, 2, 3]),
            ),
            patch("src.alerts.telegram._call_telegram", side_effect=_fake_call),
            patch("src.alerts.telegram.execute", new=AsyncMock()),
            patch("src.alerts.telegram.mark_alert_dispatched", new=AsyncMock()),
        ):
            sent = await dispatch_alert(_alert())

        assert sent == 1


class TestRegisterChat:
    @pytest.mark.asyncio
    async def test_register_chat_is_idempotent_upsert(self):
        with patch("src.alerts.telegram.execute", new=AsyncMock()) as mock_execute:
            await register_chat(42)
        mock_execute.assert_called_once()
        sql = mock_execute.call_args.args[0]
        assert "ON CONFLICT" in sql


def _snapshot(**overrides):
    from src.alerts.last_analysis import LastAnalysisSnapshot

    defaults = dict(
        ticker="NVDA",
        signal="buy",
        confidence="high",
        sentiment_score=0.42,
        risk_flags=["High valuation", "Regulatory scrutiny"],
        price_data={},
        fundamentals={},
        analysis_id="22222222-2222-2222-2222-222222222222",
        created_at=datetime.now(timezone.utc) - timedelta(hours=3),
    )
    defaults.update(overrides)
    return LastAnalysisSnapshot(**defaults)


class TestAnalysisCommand:
    @pytest.mark.asyncio
    async def test_analysis_returns_cached_snapshot(self):
        with (
            patch(
                "src.alerts.last_analysis.get_last_analysis",
                new=AsyncMock(return_value=_snapshot()),
            ),
            patch("src.alerts.telegram._call_telegram", new=AsyncMock(return_value={"ok": True})) as mock_call,
        ):
            await handle_update({"message": {"chat": {"id": 1}, "text": "/analysis nvda"}})

        mock_call.assert_called_once()
        sent_text = mock_call.call_args.args[1]["text"]
        assert "NVDA" in sent_text
        assert "BUY" in sent_text
        assert "High valuation" in sent_text
        assert "ago" in sent_text

    @pytest.mark.asyncio
    async def test_analysis_reports_no_cached_data(self):
        with (
            patch(
                "src.alerts.last_analysis.get_last_analysis",
                new=AsyncMock(return_value=None),
            ),
            patch("src.alerts.telegram.send_test_message", new=AsyncMock()) as mock_send,
        ):
            await handle_update({"message": {"chat": {"id": 1}, "text": "/analysis NVDA"}})

        sent_text = mock_send.call_args.args[1]
        assert "No cached analysis" in sent_text
        assert "/watch NVDA" in sent_text

    @pytest.mark.asyncio
    async def test_analysis_without_ticker_shows_usage(self):
        with (
            patch("src.alerts.last_analysis.get_last_analysis", new=AsyncMock()) as mock_get,
            patch("src.alerts.telegram.send_test_message", new=AsyncMock()) as mock_send,
        ):
            await handle_update({"message": {"chat": {"id": 1}, "text": "/analysis"}})

        mock_get.assert_not_called()
        assert "usage" in mock_send.call_args.args[1].lower()

    @pytest.mark.asyncio
    async def test_analysis_rejects_invalid_ticker(self):
        with (
            patch("src.alerts.last_analysis.get_last_analysis", new=AsyncMock()) as mock_get,
            patch("src.alerts.telegram.send_test_message", new=AsyncMock()) as mock_send,
        ):
            await handle_update({"message": {"chat": {"id": 1}, "text": "/analysis !!!bad!!!"}})

        mock_get.assert_not_called()
        assert "usage" in mock_send.call_args.args[1].lower()

    @pytest.mark.asyncio
    async def test_analysis_handles_lookup_failure_gracefully(self):
        with (
            patch(
                "src.alerts.last_analysis.get_last_analysis",
                new=AsyncMock(side_effect=RuntimeError("db down")),
            ),
            patch("src.alerts.telegram.send_test_message", new=AsyncMock()) as mock_send,
        ):
            await handle_update({"message": {"chat": {"id": 1}, "text": "/analysis NVDA"}})

        assert "couldn't" in mock_send.call_args.args[1].lower()


class TestBuildDigestMessage:
    def test_returns_none_for_no_monitored_tickers(self):
        from src.alerts.telegram import build_digest_message

        result = build_digest_message([], [], "https://example.com")
        assert result is None

    def test_groups_tickers_by_signal(self):
        from src.alerts.telegram import DigestTickerEntry, build_digest_message

        tickers = [
            DigestTickerEntry(ticker="NVDA", signal="buy", confidence="high"),
            DigestTickerEntry(ticker="TSLA", signal="sell", confidence="medium"),
            DigestTickerEntry(ticker="AAPL", signal="hold", confidence="low"),
        ]
        message = build_digest_message(tickers, [], "https://example.com")

        assert message is not None
        assert "BUY" in message
        assert "NVDA" in message
        assert "SELL" in message
        assert "TSLA" in message
        assert "HOLD" in message
        assert "AAPL" in message

    def test_handles_unknown_signal_as_other(self):
        from src.alerts.telegram import DigestTickerEntry, build_digest_message

        tickers = [DigestTickerEntry(ticker="XYZ", signal="insufficient_data", confidence="low")]
        message = build_digest_message(tickers, [], "https://example.com")

        assert message is not None
        assert "NO DATA" in message
        assert "XYZ" in message

    def test_includes_recent_alerts_section(self):
        from src.alerts.telegram import DigestAlertEntry, DigestTickerEntry, build_digest_message

        tickers = [DigestTickerEntry(ticker="NVDA", signal="buy", confidence="high")]
        alerts = [
            DigestAlertEntry(
                ticker="NVDA",
                severity="critical",
                alert_type="sec_filing",
                created_at=datetime.now(timezone.utc),
            )
        ]
        message = build_digest_message(tickers, alerts, "https://example.com")

        assert message is not None
        assert "Overnight activity" in message
        assert "sec_filing" in message

    def test_omits_alerts_section_when_no_recent_alerts(self):
        from src.alerts.telegram import DigestTickerEntry, build_digest_message

        tickers = [DigestTickerEntry(ticker="NVDA", signal="buy", confidence="high")]
        message = build_digest_message(tickers, [], "https://example.com")

        assert message is not None
        assert "Overnight activity" not in message

    def test_includes_dashboard_link(self):
        from src.alerts.telegram import DigestTickerEntry, build_digest_message

        tickers = [DigestTickerEntry(ticker="NVDA", signal="buy", confidence="high")]
        message = build_digest_message(tickers, [], "https://example.com")

        assert message is not None
        assert "https://example.com" in message
