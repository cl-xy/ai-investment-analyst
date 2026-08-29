"""
Full-fidelity payload linkage for promoted evaluation cases.

The full canonical payload itself is captured at analysis time (see
src/evidence/registry.py's RunEvidence.register -> evidence_artifacts.
full_payload) because it cannot be reconstructed later — by the time a
prediction resolves, the in-memory tool response and short-TTL cache row
are both gone. This module's job is narrower: for a *promoted* case, link
it to the evidence_artifacts rows from its originating run and record
whether that linkage is complete enough to support replay.

`capture_status`:
  - "complete": all linked artifacts have a non-NULL full_payload
  - "partial":  at least one artifact linked, but some/all lack full_payload
                (e.g. payload exceeded MAX_FULL_PAYLOAD_BYTES at capture time)
  - "failed":   no correlation_id, or zero artifacts found for that run_id
                (e.g. non-streaming /api/analyze path, or a pre-ledger run)

A case with capture_status != "complete" must never be used for replay
(Task 4 enforces this at read time, not just here).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

from src.db import execute, fetch, fetchrow

log = logging.getLogger(__name__)

CaptureStatus = Literal["complete", "partial", "failed"]


@dataclass(frozen=True, slots=True)
class CaptureResult:
    status: CaptureStatus
    artifact_count: int
    complete_artifact_count: int


async def capture_case_artifacts(case_id: str, correlation_id: str | None) -> CaptureResult:
    """Link a promoted case to its originating run's evidence artifacts.

    Idempotent: uses ON CONFLICT DO NOTHING on the link table's composite
    primary key, so re-running capture for the same case is a no-op after
    the first successful run.
    """
    if not correlation_id:
        log.info("eval_case_capture_skipped case_id=%s reason=no_correlation_id", case_id)
        await execute(
            "UPDATE evaluation_cases SET capture_status = 'failed', updated_at = now() WHERE id = $1",
            case_id,
        )
        return CaptureResult(status="failed", artifact_count=0, complete_artifact_count=0)

    rows = await fetch(
        """
        SELECT artifact_id, run_id, provider, tool, ticker, content_hash,
               payload_size, full_payload
        FROM evidence_artifacts
        WHERE run_id = $1
        """,
        correlation_id,
    )

    if not rows:
        log.info(
            "eval_case_capture_skipped case_id=%s reason=no_artifacts_for_run correlation_id=%s",
            case_id,
            correlation_id,
        )
        await execute(
            "UPDATE evaluation_cases SET capture_status = 'failed', updated_at = now() WHERE id = $1",
            case_id,
        )
        return CaptureResult(status="failed", artifact_count=0, complete_artifact_count=0)

    complete_count = sum(1 for r in rows if r["full_payload"] is not None)
    status: CaptureStatus = "complete" if complete_count == len(rows) else "partial"

    link_rows = [
        (
            case_id,
            r["artifact_id"],
            r["run_id"],
            r["provider"],
            r["tool"],
            r["ticker"],
            r["content_hash"],
            r["payload_size"],
        )
        for r in rows
    ]

    from src.db import executemany

    await executemany(
        """
        INSERT INTO evaluation_case_artifacts
            (case_id, artifact_id, run_id, provider, tool, ticker, content_hash, payload_size)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        ON CONFLICT (case_id, artifact_id) DO NOTHING
        """,
        link_rows,
    )

    await execute(
        "UPDATE evaluation_cases SET capture_status = $1, updated_at = now() WHERE id = $2",
        status,
        case_id,
    )

    log.info(
        "eval_case_capture_done case_id=%s status=%s artifacts=%d complete=%d",
        case_id,
        status,
        len(rows),
        complete_count,
    )
    return CaptureResult(
        status=status, artifact_count=len(rows), complete_artifact_count=complete_count
    )


async def load_case_tool_payloads(case_id: str) -> dict[str, list[dict]] | None:
    """Load full tool payloads for a case, grouped by (provider, tool).

    Returns None if the case is not capture_status='complete' — callers
    (the Task 4 replay evaluator) must treat that as "cannot replay", not
    silently fall back to partial data.
    """
    case_row = await fetchrow("SELECT capture_status FROM evaluation_cases WHERE id = $1", case_id)
    if not case_row or case_row["capture_status"] != "complete":
        return None

    rows = await fetch(
        """
        SELECT eca.provider, eca.tool, eca.ticker, ea.full_payload
        FROM evaluation_case_artifacts eca
        JOIN evidence_artifacts ea
            ON ea.artifact_id = eca.artifact_id AND ea.run_id = eca.run_id
        WHERE eca.case_id = $1
        """,
        case_id,
    )
    if not rows:
        return None

    import json as _json

    grouped: dict[str, list[dict]] = {}
    for r in rows:
        key = f"{r['provider']}:{r['tool']}"
        payload = r["full_payload"]
        if isinstance(payload, str):
            try:
                payload = _json.loads(payload)
            except (ValueError, TypeError):
                continue
        grouped.setdefault(key, []).append({"ticker": r["ticker"], "payload": payload})
    return grouped
