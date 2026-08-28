"""
Alert evaluation pipeline (orchestrator).

Wires the full chain for a monitored ticker:

    triggers -> heuristic drift scorer -> (conditional) LLM drift judge
    -> alert composer -> persistence + Telegram dispatch

`evaluate_ticker` runs this chain for one ticker. `evaluate_all_monitored`
fans it out across every currently-monitored ticker (portfolio positions +
opted-in watchlist subscriptions) with bounded concurrency, mirroring the
semaphore pattern used elsewhere in the codebase (fetch_data.py,
data_probe.py) so this doesn't compete unbounded with live user requests.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field

from src.alerts.composer import Alert, compose_alert, persist_alert
from src.alerts.data_probe import probe_ticker
from src.alerts.drift_judge import judge_drift
from src.alerts.drift_scorer import DEFAULT_DRIFT_THRESHOLD, score_drift
from src.alerts.last_analysis import LastAnalysisSnapshot, get_last_analysis
from src.alerts.telegram import dispatch_alert
from src.alerts.triggers.trigger_manager import check_all_triggers_for_ticker
from src.logging_config import get_logger
from src.metrics import metrics

log = get_logger(__name__)

_EVAL_CONCURRENCY = 3


@dataclass(frozen=True, slots=True)
class EvaluationOutcome:
    """Result of evaluating a single ticker for reasoning drift."""

    ticker: str
    evaluated: bool
    drift_score: float | None = None
    llm_invoked: bool = False
    alert: Alert | None = None
    dispatched_to: int = 0
    skip_reason: str | None = None


async def evaluate_ticker(
    ticker: str, *, correlation_id: str | None = None, dispatch: bool = True
) -> EvaluationOutcome:
    """Run the full drift-detection chain for a single ticker.

    Returns an EvaluationOutcome describing what happened, even when no
    alert was warranted — callers (the scheduled endpoint, tests) use this
    for observability rather than just a boolean.
    """
    correlation_id = correlation_id or uuid.uuid4().hex[:12]
    ticker = ticker.strip().upper()

    metrics.inc("alert_evaluations_total", labels={"ticker": ticker})

    snapshot: LastAnalysisSnapshot | None = await get_last_analysis(ticker)
    if snapshot is None:
        log.info(
            "alert_evaluation_skipped_no_baseline ticker=%s correlation_id=%s",
            ticker,
            correlation_id,
        )
        return EvaluationOutcome(ticker=ticker, evaluated=False, skip_reason="no_prior_analysis")

    probe = await probe_ticker(ticker)
    events = await check_all_triggers_for_ticker(ticker, snapshot, probe)

    # Article-count baseline comes from data_gaps-free prior news coverage,
    # which we don't persist separately — treat "no signal" gracefully by
    # falling back to the current count as its own baseline (delta = 0).
    drift = score_drift(
        previous_sentiment=snapshot.sentiment_score,
        current_sentiment=probe.sentiment_score if probe.sentiment_score is not None else snapshot.sentiment_score,
        price_at_prediction=_extract_price(snapshot),
        current_price=probe.current_price,
        previous_risk_flag_count=len(snapshot.risk_flags),
        current_risk_flag_count=len(snapshot.risk_flags),  # probe doesn't re-derive risk flags
        new_sec_filing_detected=any(e.trigger_type == "sec_filing" for e in events),
        previous_article_count=probe.article_count,
        current_article_count=probe.article_count,
        peer_signal_flipped=any(e.trigger_type == "peer_signal" for e in events),
        threshold=DEFAULT_DRIFT_THRESHOLD,
    )

    if not drift.likely_changed:
        log.info(
            "alert_evaluation_no_drift ticker=%s score=%.3f correlation_id=%s",
            ticker,
            drift.score,
            correlation_id,
        )
        return EvaluationOutcome(ticker=ticker, evaluated=True, drift_score=drift.score)

    judgment = None
    llm_invoked = False
    judge_result = await judge_drift(ticker, snapshot, events)
    llm_invoked = judge_result.llm_invoked
    judgment = judge_result.judgment

    if llm_invoked and judgment is not None:
        metrics.inc("alert_llm_judgments_total", labels={"changed": str(judgment.changed)})
    elif not llm_invoked:
        metrics.inc("alert_heuristic_only_total")

    alert = compose_alert(ticker, snapshot, drift, events, judgment, llm_invoked)

    try:
        await persist_alert(alert)
    except Exception:
        log.exception("alert_persist_failed ticker=%s correlation_id=%s", ticker, correlation_id)

    metrics.inc("alerts_fired_total", labels={"severity": alert.severity})

    dispatched_to = 0
    if dispatch:
        try:
            dispatched_to = await dispatch_alert(alert)
        except Exception:
            log.exception(
                "alert_dispatch_failed ticker=%s correlation_id=%s", ticker, correlation_id
            )

    log.info(
        "alert_evaluation_complete ticker=%s score=%.3f severity=%s dispatched_to=%d correlation_id=%s",
        ticker,
        drift.score,
        alert.severity,
        dispatched_to,
        correlation_id,
    )

    return EvaluationOutcome(
        ticker=ticker,
        evaluated=True,
        drift_score=drift.score,
        llm_invoked=llm_invoked,
        alert=alert,
        dispatched_to=dispatched_to,
    )


def _extract_price(snapshot: LastAnalysisSnapshot) -> float | None:
    from src.api.persistence import extract_current_price

    return extract_current_price(snapshot.price_data)


async def get_monitored_tickers() -> list[str]:
    """Union of portfolio positions (SQLite) and active watchlist alert
    subscriptions (Postgres). Deduplicated, order-preserving."""
    from src.alerts.subscriptions import get_active_subscription_tickers
    from src.mcp_servers.portfolio_server import fetch_all_positions

    seen: set[str] = set()
    tickers: list[str] = []

    try:
        positions = await fetch_all_positions()
        for pos in positions:
            ticker = str(pos.get("ticker", "")).strip().upper()
            if ticker and ticker not in seen:
                seen.add(ticker)
                tickers.append(ticker)
    except Exception:
        log.warning("get_monitored_tickers_portfolio_failed", exc_info=True)

    try:
        subscribed = await get_active_subscription_tickers()
        for ticker in subscribed:
            normalized = ticker.strip().upper()
            if normalized and normalized not in seen:
                seen.add(normalized)
                tickers.append(normalized)
    except Exception:
        log.warning("get_monitored_tickers_subscriptions_failed", exc_info=True)

    return tickers


@dataclass(frozen=True, slots=True)
class PipelineRunSummary:
    """Aggregate result of an evaluate_all_monitored() pass."""

    tickers_evaluated: int
    alerts_fired: int
    llm_calls_used: int
    heuristic_only_count: int
    outcomes: list[EvaluationOutcome] = field(default_factory=list)


async def evaluate_all_monitored(*, correlation_id: str | None = None) -> PipelineRunSummary:
    """Evaluate every currently-monitored ticker with bounded concurrency."""
    correlation_id = correlation_id or uuid.uuid4().hex[:12]
    tickers = await get_monitored_tickers()

    if not tickers:
        log.info("alert_pipeline_run_skipped_no_monitored_tickers correlation_id=%s", correlation_id)
        return PipelineRunSummary(
            tickers_evaluated=0, alerts_fired=0, llm_calls_used=0, heuristic_only_count=0
        )

    semaphore = asyncio.Semaphore(_EVAL_CONCURRENCY)

    async def _bounded(ticker: str) -> EvaluationOutcome:
        async with semaphore:
            try:
                return await evaluate_ticker(ticker, correlation_id=correlation_id)
            except Exception:
                log.exception(
                    "alert_evaluation_task_failed ticker=%s correlation_id=%s",
                    ticker,
                    correlation_id,
                )
                return EvaluationOutcome(ticker=ticker, evaluated=False, skip_reason="task_error")

    outcomes = await asyncio.gather(*[_bounded(t) for t in tickers])

    alerts_fired = sum(1 for o in outcomes if o.alert is not None)
    llm_calls_used = sum(1 for o in outcomes if o.llm_invoked)
    heuristic_only = sum(
        1 for o in outcomes if o.alert is not None and not o.llm_invoked
    )

    log.info(
        "alert_pipeline_run_complete tickers=%d alerts_fired=%d llm_calls=%d correlation_id=%s",
        len(outcomes),
        alerts_fired,
        llm_calls_used,
        correlation_id,
    )

    return PipelineRunSummary(
        tickers_evaluated=len(outcomes),
        alerts_fired=alerts_fired,
        llm_calls_used=llm_calls_used,
        heuristic_only_count=heuristic_only,
        outcomes=outcomes,
    )
