"""
Alert composer: turns a drift-scoring result (+ optional LLM judgment) into
a structured, human-readable Alert, and persists it.

Severity model:
  - info:     heuristic score crossed the threshold but no LLM judgment was
              obtained (budget exhausted / call failed) — surfaced for
              visibility, not urgency.
  - warning:  LLM judge ran but did not confirm a verdict change (drift was
              real but not thesis-breaking), OR judge wasn't run and the
              heuristic score is high.
  - critical: LLM judge confirmed the verdict would likely change.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from src.alerts.drift_judge import DriftJudgment
from src.alerts.drift_scorer import DriftResult
from src.alerts.last_analysis import LastAnalysisSnapshot
from src.alerts.triggers.events import TriggerEvent
from src.db import execute, fetchrow
from src.logging_config import get_logger

log = get_logger(__name__)

Severity = str  # "info" | "warning" | "critical"


@dataclass(frozen=True, slots=True)
class Alert:
    """Fully composed alert, ready for persistence and/or Telegram dispatch."""

    id: str
    ticker: str
    alert_type: str
    severity: Severity
    drift_score: float
    old_signal: str | None
    new_signal: str | None
    reasoning_diff: dict
    triggered_by: list[str]
    llm_judged: bool
    created_at: datetime


def _primary_alert_type(events: list[TriggerEvent]) -> str:
    """Pick a representative alert_type for the row when multiple triggers
    fired. Priority: sec_filing > peer_signal > sentiment > price, since a
    filing is the most concrete/actionable signal."""
    priority = ["sec_filing", "peer_signal", "sentiment", "price"]
    fired_types = {e.trigger_type for e in events}
    for candidate in priority:
        if candidate in fired_types:
            return candidate
    return "drift_score"


def _severity_for(drift: DriftResult, judgment: DriftJudgment | None, llm_invoked: bool) -> str:
    if llm_invoked and judgment is not None:
        return "critical" if judgment.changed else "warning"
    if llm_invoked and judgment is None:
        # LLM ran but parsing/call failed — heuristic score alone still stands
        return "warning" if drift.score >= drift.threshold else "info"
    # LLM was never invoked (budget exhausted / not escalated)
    return "warning" if drift.likely_changed else "info"


def _build_reasoning_diff(
    snapshot: LastAnalysisSnapshot,
    drift: DriftResult,
    events: list[TriggerEvent],
    judgment: DriftJudgment | None,
) -> dict:
    """Structured diff explaining *why* this alert fired — the core
    differentiator versus a plain price-threshold alert."""
    return {
        "drift_score": round(drift.score, 4),
        "drift_threshold": drift.threshold,
        "components": {
            "sentiment_delta": round(drift.components.sentiment_delta, 4),
            "price_move_pct": round(drift.components.price_move_pct, 4),
            "risk_flag_count_delta": round(drift.components.risk_flag_count_delta, 4),
            "new_sec_filing": drift.components.new_sec_filing,
            "news_volume_spike": round(drift.components.news_volume_spike, 4),
            "peer_signal_flip": drift.components.peer_signal_flip,
        },
        "details": drift.details,
        "triggered_events": [
            {"type": e.trigger_type, "summary": e.summary, "metadata": e.metadata}
            for e in events
        ],
        "prior_signal": snapshot.signal,
        "prior_confidence": snapshot.confidence,
        "llm_judgment": (
            {
                "changed": judgment.changed,
                "new_signal": judgment.new_signal,
                "reasoning": judgment.reasoning,
                "key_shifts": judgment.key_shifts,
            }
            if judgment is not None
            else None
        ),
    }


def compose_alert(
    ticker: str,
    snapshot: LastAnalysisSnapshot,
    drift: DriftResult,
    events: list[TriggerEvent],
    judgment: DriftJudgment | None,
    llm_invoked: bool,
) -> Alert:
    """Pure composition step (no I/O) — build the Alert object. Callers
    persist it separately via persist_alert()."""
    new_signal = judgment.new_signal if judgment is not None and judgment.new_signal else None
    severity = _severity_for(drift, judgment, llm_invoked)

    return Alert(
        id=str(uuid.uuid4()),
        ticker=ticker,
        alert_type=_primary_alert_type(events),
        severity=severity,
        drift_score=drift.score,
        old_signal=snapshot.signal,
        new_signal=new_signal,
        reasoning_diff=_build_reasoning_diff(snapshot, drift, events, judgment),
        triggered_by=[e.trigger_type for e in events],
        llm_judged=llm_invoked and judgment is not None,
        created_at=datetime.now(timezone.utc),
    )


async def persist_alert(alert: Alert) -> None:
    """Insert the alert into the `alerts` table."""
    import json

    await execute(
        """
        INSERT INTO alerts (
            id, ticker, alert_type, severity, drift_score,
            old_signal, new_signal, reasoning_diff, triggered_by,
            llm_judged, dispatched_telegram, created_at
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, FALSE, $11)
        """,
        uuid.UUID(alert.id),
        alert.ticker,
        alert.alert_type,
        alert.severity,
        alert.drift_score,
        alert.old_signal,
        alert.new_signal,
        json.dumps(alert.reasoning_diff, default=str),
        json.dumps(alert.triggered_by),
        alert.llm_judged,
        alert.created_at,
    )
    log.info(
        "alert_persisted id=%s ticker=%s severity=%s score=%.3f",
        alert.id,
        alert.ticker,
        alert.severity,
        alert.drift_score,
    )


async def mark_alert_dispatched(alert_id: str) -> None:
    """Flag an alert as having been sent via Telegram (idempotency marker for
    the dispatcher's own bookkeeping; does not affect acknowledgment state)."""
    await execute(
        "UPDATE alerts SET dispatched_telegram = TRUE WHERE id = $1",
        uuid.UUID(alert_id),
    )


async def get_alert(alert_id: str) -> dict | None:
    """Fetch a single alert by id, for round-trip verification / API reads."""
    row = await fetchrow("SELECT * FROM alerts WHERE id = $1", uuid.UUID(alert_id))
    if row is None:
        return None
    return dict(row)
