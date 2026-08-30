"""
Telegram bot integration for Reasoning-Aware Signal Alerts.

Single bot-per-deployment model: one bot token serves every user who sends
/start. No per-user OAuth — this is a demo-scale feature, not a multi-tenant
SaaS. Uses the raw Telegram Bot API via httpx (no heavyweight SDK needed for
the handful of calls this requires: sendMessage, setWebhook, getMe).

Webhook auth: Telegram lets you configure a secret token that it echoes back
in the `X-Telegram-Bot-Api-Secret-Token` header on every webhook POST — this
is what we validate against, since Telegram doesn't support custom auth
headers on the outbound webhook calls it makes to us.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

from src.alerts.composer import Alert, mark_alert_dispatched
from src.db import execute, fetch, fetchrow
from src.logging_config import get_logger

log = get_logger(__name__)

_TELEGRAM_API_BASE = "https://api.telegram.org/bot{token}"
_REQUEST_TIMEOUT = 10.0

# Rate limit: don't spam the same ticker more than once per this window,
# independent of severity or which chat(s) are subscribed.
_DISPATCH_COOLDOWN_HOURS = 4

_SIGNAL_EMOJI = {"buy": "\U0001f7e2", "hold": "\U0001f7e1", "sell": "\U0001f534"}
_SEVERITY_EMOJI = {"critical": "\U0001f6a8", "warning": "\u26a0\ufe0f", "info": "\u2139\ufe0f"}


def _api_url(method: str) -> str:
    from src.config import settings

    return f"{_TELEGRAM_API_BASE.format(token=settings.telegram_bot_token)}/{method}"


async def _call_telegram(method: str, payload: dict) -> dict | None:
    from src.config import settings

    if not settings.telegram_bot_token:
        log.warning("telegram_call_skipped_no_token method=%s", method)
        return None
    try:
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
            resp = await client.post(_api_url(method), json=payload)
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        log.warning("telegram_call_failed method=%s error=%s", method, exc)
        return None


# --- Registration -----------------------------------------------------------


async def register_chat(chat_id: int) -> None:
    """Upsert a chat_id as an active subscriber (idempotent for repeated /start)."""
    await execute(
        """
        INSERT INTO telegram_registrations (chat_id, registered_at, active)
        VALUES ($1, $2, TRUE)
        ON CONFLICT (chat_id) DO UPDATE SET active = TRUE
        """,
        chat_id,
        datetime.now(timezone.utc),
    )


async def deactivate_chat(chat_id: int) -> None:
    """Mark a chat_id inactive (in response to /stop). Row is kept for
    audit/re-activation rather than deleted."""
    await execute("UPDATE telegram_registrations SET active = FALSE WHERE chat_id = $1", chat_id)


async def get_active_chat_ids() -> list[int]:
    rows = await fetch("SELECT chat_id FROM telegram_registrations WHERE active = TRUE")
    return [row["chat_id"] for row in rows]


async def is_chat_registered(chat_id: int) -> bool:
    row = await fetchrow("SELECT active FROM telegram_registrations WHERE chat_id = $1", chat_id)
    return bool(row and row["active"])


# --- Message formatting ------------------------------------------------------


def _format_alert_message(alert: Alert, frontend_url: str) -> str:
    severity_icon = _SEVERITY_EMOJI.get(alert.severity, "\u2139\ufe0f")
    old_icon = _SIGNAL_EMOJI.get((alert.old_signal or "").lower(), "")
    new_icon = _SIGNAL_EMOJI.get((alert.new_signal or "").lower(), "")

    lines = [f"{severity_icon} *{alert.ticker}* — reasoning drift detected"]

    if alert.new_signal and alert.old_signal and alert.new_signal != alert.old_signal:
        lines.append(
            f"Signal: {old_icon} {alert.old_signal.upper()} \u2192 {new_icon} {alert.new_signal.upper()}"
        )
    else:
        lines.append(f"Prior signal: {old_icon} {(alert.old_signal or 'unknown').upper()}")

    lines.append(f"Drift score: {alert.drift_score:.2f}")

    llm_judgment = alert.reasoning_diff.get("llm_judgment")
    key_shifts = (llm_judgment or {}).get("key_shifts") or []
    if key_shifts:
        lines.append("\nWhat changed:")
        for shift in key_shifts[:5]:
            lines.append(f"\u2022 {shift}")
    else:
        events = alert.reasoning_diff.get("triggered_events") or []
        if events:
            lines.append("\nWhat changed:")
            for event in events[:5]:
                lines.append(f"\u2022 {event.get('summary', '')}")

    if llm_judgment and llm_judgment.get("reasoning"):
        lines.append(f"\n_{llm_judgment['reasoning']}_")

    deep_link = f"{frontend_url}/analyze?tickers={alert.ticker}"
    lines.append(f"\n[View full analysis]({deep_link})")

    return "\n".join(lines)


# --- Dispatch -----------------------------------------------------------


async def _dispatch_allowed(ticker: str) -> bool:
    """Atomic-ish check-and-set for the per-ticker cooldown window. Not a hard
    guarantee under concurrent evaluation runs, but the evaluation pipeline
    already limits ticker concurrency, so races are unlikely in practice."""
    row = await fetchrow(
        "SELECT last_dispatched_at FROM alert_dispatch_state WHERE ticker = $1", ticker
    )
    if row is not None:
        elapsed_hours = (
            datetime.now(timezone.utc) - row["last_dispatched_at"]
        ).total_seconds() / 3600.0
        if elapsed_hours < _DISPATCH_COOLDOWN_HOURS:
            return False

    await execute(
        """
        INSERT INTO alert_dispatch_state (ticker, last_dispatched_at)
        VALUES ($1, $2)
        ON CONFLICT (ticker) DO UPDATE SET last_dispatched_at = EXCLUDED.last_dispatched_at
        """,
        ticker,
        datetime.now(timezone.utc),
    )
    return True


async def dispatch_alert(alert: Alert, *, force: bool = False) -> int:
    """Send `alert` to every registered chat. Rate-limited per-ticker unless
    `force` is set (e.g. for a manual test dispatch). Returns the number of
    chats the message was successfully sent to."""
    from src.config import settings

    if not force and not await _dispatch_allowed(alert.ticker):
        log.info("telegram_dispatch_skipped_cooldown ticker=%s", alert.ticker)
        return 0

    chat_ids = await get_active_chat_ids()
    if not chat_ids:
        log.info("telegram_dispatch_skipped_no_subscribers ticker=%s", alert.ticker)
        return 0

    message = _format_alert_message(alert, settings.frontend_url)

    sent = 0
    for chat_id in chat_ids:
        result = await _call_telegram(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True,
            },
        )
        if result is not None and result.get("ok"):
            sent += 1
            await execute(
                "UPDATE telegram_registrations SET last_alert_sent_at = $1 WHERE chat_id = $2",
                datetime.now(timezone.utc),
                chat_id,
            )

    if sent > 0:
        await mark_alert_dispatched(alert.id)

    log.info(
        "telegram_dispatch_complete ticker=%s sent=%d total=%d", alert.ticker, sent, len(chat_ids)
    )
    return sent


async def send_test_message(chat_id: int, text: str) -> bool:
    """Used by the /status command and manual verification."""
    result = await _call_telegram("sendMessage", {"chat_id": chat_id, "text": text})
    return bool(result and result.get("ok"))


# --- Webhook command handling ------------------------------------------------


async def handle_update(update: dict) -> None:
    """Process a single Telegram Update payload (from the webhook route)."""
    message = update.get("message")
    if not isinstance(message, dict):
        return

    chat = message.get("chat", {})
    chat_id = chat.get("id")
    text = (message.get("text") or "").strip()
    if not isinstance(chat_id, int):
        return

    # Match on the first whitespace-separated token so prefix commands like
    # /watch don't accidentally swallow /watching.
    command = text.split()[0].lower() if text else ""

    if command == "/start":
        await register_chat(chat_id)
        await send_test_message(
            chat_id,
            "You're subscribed to Reasoning-Aware Signal Alerts. "
            "You'll be notified when the investment thesis for a monitored "
            "ticker materially changes — not just when the price moves. "
            "Send /stop to unsubscribe, /status to check your subscription.\n\n"
            "Use /watch TICKER to add a ticker to your alert watchlist, "
            "/unwatch TICKER to remove one, and /watching to see your list.\n\n"
            "Use /analysis TICKER to look up the latest cached analysis.",
        )
    elif command == "/stop":
        await deactivate_chat(chat_id)
        await send_test_message(chat_id, "Unsubscribed. Send /start to resume alerts.")
    elif command == "/status":
        registered = await is_chat_registered(chat_id)
        status_text = (
            "You are subscribed to alerts."
            if registered
            else "You are not subscribed. Send /start to subscribe."
        )
        await send_test_message(chat_id, status_text)
    elif command == "/watch":
        await _handle_watch_command(chat_id, text)
    elif command == "/unwatch":
        await _handle_unwatch_command(chat_id, text)
    elif command == "/watching":
        await _handle_watching_command(chat_id)
    elif command == "/analysis":
        await _handle_analysis_command(chat_id, text)
    else:
        await send_test_message(
            chat_id,
            "Commands: /start (subscribe), /stop (unsubscribe), /status, "
            "/watch TICKER, /unwatch TICKER, /watching, /analysis TICKER",
        )


def _parse_ticker_arg(text: str, command: str) -> str | None:
    """Extract and validate a single ticker argument from a command like
    '/watch NVDA'. Returns None if missing or invalid."""
    from src.api.schemas import VALID_TICKER_RE

    remainder = text[len(command) :].strip()
    if not remainder:
        return None
    # Only take the first whitespace-separated token; ignore trailing junk.
    ticker = remainder.split()[0].strip().upper()
    if not VALID_TICKER_RE.match(ticker):
        return None
    return ticker


async def _handle_watch_command(chat_id: int, text: str) -> None:
    from src.alerts.subscriptions import subscribe_ticker

    ticker = _parse_ticker_arg(text, "/watch")
    if not ticker:
        await send_test_message(
            chat_id, "Usage: /watch TICKER (e.g. /watch NVDA)"
        )
        return

    try:
        await subscribe_ticker(ticker, source="telegram")
    except Exception:
        log.exception("telegram_watch_command_failed chat_id=%s ticker=%s", chat_id, ticker)
        await send_test_message(
            chat_id, f"Couldn't add {ticker} to your watchlist. Please try again."
        )
        return

    await send_test_message(
        chat_id,
        f"Watching {ticker}. You'll get an alert if its investment thesis "
        "materially shifts. Send /unwatch " + ticker + " to stop.",
    )


async def _handle_unwatch_command(chat_id: int, text: str) -> None:
    from src.alerts.subscriptions import unsubscribe_ticker

    ticker = _parse_ticker_arg(text, "/unwatch")
    if not ticker:
        await send_test_message(
            chat_id, "Usage: /unwatch TICKER (e.g. /unwatch NVDA)"
        )
        return

    try:
        removed = await unsubscribe_ticker(ticker)
    except Exception:
        log.exception("telegram_unwatch_command_failed chat_id=%s ticker=%s", chat_id, ticker)
        await send_test_message(
            chat_id, f"Couldn't remove {ticker} from your watchlist. Please try again."
        )
        return

    if removed:
        await send_test_message(chat_id, f"Stopped watching {ticker}.")
    else:
        await send_test_message(chat_id, f"{ticker} wasn't on your watchlist.")


async def _handle_watching_command(chat_id: int) -> None:
    from src.alerts.subscriptions import list_subscriptions

    try:
        subs = await list_subscriptions()
    except Exception:
        log.exception("telegram_watching_command_failed chat_id=%s", chat_id)
        await send_test_message(chat_id, "Couldn't load your watchlist. Please try again.")
        return

    if not subs:
        await send_test_message(
            chat_id, "You're not watching any tickers yet. Use /watch TICKER to add one."
        )
        return

    tickers = ", ".join(sorted(s.ticker for s in subs))
    await send_test_message(chat_id, f"Watching: {tickers}")


def _format_age(created_at: datetime) -> str:
    """Human-readable "time since" for a cached analysis timestamp."""
    delta = datetime.now(timezone.utc) - created_at
    total_seconds = delta.total_seconds()
    if total_seconds < 3600:
        minutes = max(1, int(total_seconds // 60))
        return f"{minutes}m ago"
    if total_seconds < 86400:
        hours = int(total_seconds // 3600)
        return f"{hours}h ago"
    days = int(total_seconds // 86400)
    return f"{days}d ago"


def _format_analysis_message(snapshot, frontend_url: str) -> str:
    """Format a cached LastAnalysisSnapshot for the /analysis command reply.
    Reuses the same signal emoji convention as alert messages."""
    signal_icon = _SIGNAL_EMOJI.get((snapshot.signal or "").lower(), "")

    lines = [f"{signal_icon} *{snapshot.ticker}* — {(snapshot.signal or 'unknown').upper()}"]
    lines.append(f"Confidence: {snapshot.confidence}")
    lines.append(f"Sentiment: {snapshot.sentiment_score:.2f}")

    if snapshot.risk_flags:
        lines.append("\nRisk flags:")
        for flag in snapshot.risk_flags[:5]:
            lines.append(f"\u2022 {flag}")

    lines.append(f"\nLast analyzed {_format_age(snapshot.created_at)}")

    deep_link = f"{frontend_url}/analyze?tickers={snapshot.ticker}"
    lines.append(f"\n[View full analysis]({deep_link})")

    return "\n".join(lines)


async def _handle_analysis_command(chat_id: int, text: str) -> None:
    """Look up the most recent cached analysis for a ticker. Read-only —
    never triggers a fresh analysis or any LLM call, just formats whatever
    is already in ticker_analyses."""
    from src.alerts.last_analysis import get_last_analysis
    from src.config import settings

    ticker = _parse_ticker_arg(text, "/analysis")
    if not ticker:
        await send_test_message(
            chat_id, "Usage: /analysis TICKER (e.g. /analysis NVDA)"
        )
        return

    try:
        snapshot = await get_last_analysis(ticker)
    except Exception:
        log.exception("telegram_analysis_command_failed chat_id=%s ticker=%s", chat_id, ticker)
        await send_test_message(
            chat_id, f"Couldn't look up {ticker} right now. Please try again."
        )
        return

    if snapshot is None:
        await send_test_message(
            chat_id,
            f"No cached analysis for {ticker} yet. Add it to your watchlist "
            f"with /watch {ticker} or analyze it in the app first.",
        )
        return

    message = _format_analysis_message(snapshot, settings.frontend_url)
    await _call_telegram(
        "sendMessage",
        {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        },
    )


# --- Daily digest ------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DigestTickerEntry:
    """Minimal per-ticker projection the digest builder needs — decoupled
    from LastAnalysisSnapshot so this stays a pure, DB-free function."""

    ticker: str
    signal: str
    confidence: str


@dataclass(frozen=True, slots=True)
class DigestAlertEntry:
    """Minimal per-alert projection for the "overnight activity" section."""

    ticker: str
    severity: str
    alert_type: str
    created_at: datetime


def build_digest_message(
    tickers: list[DigestTickerEntry],
    recent_alerts: list[DigestAlertEntry],
    frontend_url: str,
) -> str | None:
    """Pure formatter: build the daily digest text from already-cached
    per-ticker signals and recent alert history. Returns None when there is
    nothing to report (no monitored tickers), so callers can skip sending an
    empty digest without needing their own guard logic."""
    if not tickers:
        return None

    lines = ["\U0001f4ca *Daily Digest*"]

    by_signal: dict[str, list[DigestTickerEntry]] = {"buy": [], "hold": [], "sell": [], "other": []}
    for entry in tickers:
        key = entry.signal.lower() if entry.signal.lower() in by_signal else "other"
        by_signal[key].append(entry)

    for signal_key in ("buy", "hold", "sell", "other"):
        entries = by_signal[signal_key]
        if not entries:
            continue
        icon = _SIGNAL_EMOJI.get(signal_key, "")
        label = signal_key.upper() if signal_key != "other" else "NO DATA"
        lines.append(f"\n{icon} *{label}*")
        for entry in sorted(entries, key=lambda e: e.ticker):
            lines.append(f"\u2022 {entry.ticker} ({entry.confidence} confidence)")

    if recent_alerts:
        lines.append("\n\u26a1 *Overnight activity*")
        for alert in sorted(recent_alerts, key=lambda a: a.created_at, reverse=True)[:10]:
            severity_icon = _SEVERITY_EMOJI.get(alert.severity, "")
            lines.append(f"\u2022 {severity_icon} {alert.ticker} — {alert.alert_type}")

    lines.append(f"\n[Open dashboard]({frontend_url})")

    return "\n".join(lines)


def validate_webhook_secret(header_value: str | None) -> bool:
    """Compare the X-Telegram-Bot-Api-Secret-Token header against the
    configured secret. Timing-safe comparison via hmac.compare_digest."""
    import hmac

    from src.config import settings

    expected = settings.telegram_webhook_secret
    if not expected:
        # No secret configured means the webhook endpoint is not usable;
        # fail closed rather than accepting unauthenticated updates.
        return False
    if not header_value:
        return False
    return hmac.compare_digest(header_value, expected)
