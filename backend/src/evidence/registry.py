"""
Evidence Registry: canonical artifact ID generation and persistence.

This is the SINGLE source of artifact identity in the system. Every piece
of retrieved data gets a stable, content-addressed ID generated here.
No other module should generate source/artifact IDs.

Artifact ID format: ev_{sha256(provider|tool|ticker|canonical_content)[:16]}
- Deterministic: same content always gets the same ID
- Content-addressed: changes in data produce new IDs
- Excludes volatile fields (retrieval time, cache status) from the hash
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from src.db import execute, executemany, fetch, fetchrow


# ---------------------------------------------------------------------------
# Artifact model
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EvidenceArtifact:
    """Immutable evidence artifact with provenance metadata."""

    artifact_id: str
    content_hash: str
    provider: str
    tool: str
    ticker: str
    retrieved_at: datetime
    cache_hit: bool
    payload_excerpt: str  # first 500 chars for audit display
    payload_size: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "content_hash": self.content_hash,
            "provider": self.provider,
            "tool": self.tool,
            "ticker": self.ticker,
            "retrieved_at": self.retrieved_at.isoformat(),
            "cache_hit": self.cache_hit,
            "payload_excerpt": self.payload_excerpt,
            "payload_size": self.payload_size,
        }


# ---------------------------------------------------------------------------
# ID generation (deterministic, content-addressed)
# ---------------------------------------------------------------------------


def _canonicalize(content: Any) -> str:
    """Produce a deterministic string from any JSON-serializable content.

    Uses sorted keys and no whitespace to ensure identical content
    always produces the same hash regardless of dict ordering.
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    return json.dumps(content, sort_keys=True, separators=(",", ":"), default=str)


def make_artifact_id(provider: str, tool: str, ticker: str, content: Any) -> str:
    """Generate a canonical, deterministic artifact ID.

    The ID is derived from the content itself (content-addressed),
    so identical data from the same provider/tool/ticker always
    gets the same ID. Volatile fields (timestamps, cache status)
    are excluded from the hash.
    """
    canonical = _canonicalize(content)
    hash_input = f"{provider}|{tool}|{ticker}|{canonical}"
    content_hash = hashlib.sha256(hash_input.encode()).hexdigest()
    return f"ev_{content_hash[:16]}"


def compute_content_hash(content: Any) -> str:
    """Full SHA-256 of canonicalized content for integrity verification."""
    canonical = _canonicalize(content)
    return hashlib.sha256(canonical.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Registry: batch registration of artifacts per run
# ---------------------------------------------------------------------------


@dataclass
class RunEvidence:
    """Collects all evidence artifacts for a single analysis run."""

    run_id: str
    artifacts: dict[str, EvidenceArtifact] = field(default_factory=dict)
    _registered_at: float = field(default_factory=time.time)

    def register(
        self,
        provider: str,
        tool: str,
        ticker: str,
        content: Any,
        cache_hit: bool = False,
    ) -> EvidenceArtifact:
        """Register a piece of evidence and return its artifact."""
        artifact_id = make_artifact_id(provider, tool, ticker, content)
        content_hash = compute_content_hash(content)
        canonical = _canonicalize(content)

        artifact = EvidenceArtifact(
            artifact_id=artifact_id,
            content_hash=content_hash,
            provider=provider,
            tool=tool,
            ticker=ticker,
            retrieved_at=datetime.now(timezone.utc),
            cache_hit=cache_hit,
            payload_excerpt=canonical[:500],
            payload_size=len(canonical),
        )
        self.artifacts[artifact_id] = artifact
        return artifact

    def get_valid_ids(self) -> set[str]:
        """Return set of all valid artifact IDs for this run (for citation validation)."""
        return set(self.artifacts.keys())

    def to_manifest(self) -> list[dict[str, Any]]:
        """Export all artifacts as a list of dicts for the audit bundle."""
        return [a.to_dict() for a in self.artifacts.values()]


# ---------------------------------------------------------------------------
# Citation validation
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CitationValidationResult:
    """Result of validating a single citation against the evidence ledger."""

    source_id: str
    claim: str
    provider: str
    resolved: bool
    reason: str  # "valid", "not_in_run", "malformed", "legacy_unverified"


def validate_citations(
    citations: list[dict[str, Any]],
    run_evidence: RunEvidence,
) -> tuple[list[CitationValidationResult], float]:
    """Validate citations against run evidence. Returns results and confidence adjustment.

    This is O(n) set lookup against in-memory artifact IDs. Zero DB queries.
    Designed to add zero latency to the hot path.

    Returns:
        (validation_results, confidence_multiplier)
        confidence_multiplier is 1.0 if all valid, reduced for invalid citations
    """
    valid_ids = run_evidence.get_valid_ids()
    results: list[CitationValidationResult] = []
    invalid_count = 0

    for citation in citations:
        source_id = citation.get("source_id", "")
        claim = citation.get("claim", "")
        provider = citation.get("provider", "")

        if not source_id:
            results.append(
                CitationValidationResult(
                    source_id=source_id,
                    claim=claim,
                    provider=provider,
                    resolved=False,
                    reason="malformed",
                )
            )
            invalid_count += 1
        elif source_id.startswith("ev_") and source_id in valid_ids:
            results.append(
                CitationValidationResult(
                    source_id=source_id,
                    claim=claim,
                    provider=provider,
                    resolved=True,
                    reason="valid",
                )
            )
        elif source_id.startswith("ev_"):
            # Has artifact format but not in this run
            results.append(
                CitationValidationResult(
                    source_id=source_id,
                    claim=claim,
                    provider=provider,
                    resolved=False,
                    reason="not_in_run",
                )
            )
            invalid_count += 1
        else:
            # Legacy format (pre-ledger): cannot verify provenance, counts as invalid
            results.append(
                CitationValidationResult(
                    source_id=source_id,
                    claim=claim,
                    provider=provider,
                    resolved=False,
                    reason="legacy_unverified",
                )
            )
            invalid_count += 1

    # Confidence multiplier: reduce by 15% per invalid citation, floor at 0.5
    if invalid_count == 0:
        multiplier = 1.0
    else:
        total = len(citations) if citations else 1
        invalid_ratio = invalid_count / total
        multiplier = max(0.5, 1.0 - (invalid_ratio * 0.3))

    return results, multiplier


# ---------------------------------------------------------------------------
# Persistence: store artifacts and validation results in PostgreSQL
# ---------------------------------------------------------------------------


async def persist_run_evidence(run_evidence: RunEvidence) -> None:
    """Persist all evidence artifacts for a run to PostgreSQL.

    Uses INSERT ON CONFLICT DO NOTHING for deduplication (same content
    produces same artifact_id, so duplicates are harmless).
    """
    if not run_evidence.artifacts:
        return

    rows = [
        (
            a.artifact_id,
            a.content_hash,
            a.provider,
            a.tool,
            a.ticker,
            run_evidence.run_id,
            a.retrieved_at,
            a.cache_hit,
            a.payload_excerpt,
            a.payload_size,
        )
        for a in run_evidence.artifacts.values()
    ]

    await executemany(
        """
        INSERT INTO evidence_artifacts
            (artifact_id, content_hash, provider, tool, ticker, run_id,
             retrieved_at, cache_hit, payload_excerpt, payload_size)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
        ON CONFLICT (artifact_id, run_id) DO NOTHING
        """,
        rows,
    )


async def persist_citation_validation(
    run_id: str,
    results: list[CitationValidationResult] | list[dict[str, Any]],
    confidence_multiplier: float,
    original_confidence: str,
    adjusted_confidence: str,
) -> None:
    """Persist citation validation results for audit trail."""
    # Handle both CitationValidationResult objects and pre-serialized dicts
    serialized_results = []
    for r in results:
        if isinstance(r, dict):
            serialized_results.append(r)
        else:
            serialized_results.append(
                {
                    "source_id": r.source_id,
                    "claim": r.claim,
                    "provider": r.provider,
                    "resolved": r.resolved,
                    "reason": r.reason,
                }
            )

    validation_data = {
        "results": serialized_results,
        "confidence_multiplier": confidence_multiplier,
        "original_confidence": original_confidence,
        "adjusted_confidence": adjusted_confidence,
        "validated_at": datetime.now(timezone.utc).isoformat(),
    }

    await execute(
        """
        INSERT INTO citation_validations (run_id, validation_data)
        VALUES ($1, $2::jsonb)
        ON CONFLICT (run_id) DO UPDATE SET validation_data = EXCLUDED.validation_data
        """,
        run_id,
        json.dumps(validation_data),
    )


# ---------------------------------------------------------------------------
# Audit bundle export
# ---------------------------------------------------------------------------


async def get_audit_bundle(run_id: str) -> dict[str, Any] | None:
    """Build a complete audit bundle for a run.

    Contains: run metadata, all evidence artifacts, citation validation,
    and integrity hashes for reproducibility verification.
    """
    # Fetch run metadata
    run_row = await fetchrow(
        "SELECT * FROM runs WHERE run_id = $1",
        run_id,
    )
    if not run_row:
        return None

    # Fetch all artifacts for this run
    artifact_rows = await fetch(
        """
        SELECT artifact_id, content_hash, provider, tool, ticker,
               retrieved_at, cache_hit, payload_excerpt, payload_size
        FROM evidence_artifacts
        WHERE run_id = $1
        ORDER BY retrieved_at
        """,
        run_id,
    )

    # Fetch citation validation
    validation_row = await fetchrow(
        "SELECT validation_data FROM citation_validations WHERE run_id = $1",
        run_id,
    )

    # Fetch the analysis result
    analysis_rows = await fetch(
        """
        SELECT ticker, signal, confidence, thesis, citations, data_gaps
        FROM ticker_analyses
        WHERE run_id = $1
        """,
        run_id,
    )

    # Build the bundle
    bundle = {
        "version": "1.0",
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_metadata": {
            "started_at": run_row["started_at"].isoformat() if run_row.get("started_at") else None,
            "completed_at": (
                run_row["completed_at"].isoformat() if run_row.get("completed_at") else None
            ),
            "duration_ms": run_row.get("duration_ms"),
            "router_model": run_row.get("router_model"),
            "analysis_model": run_row.get("analysis_model"),
            "total_tokens": run_row.get("total_tokens"),
        },
        "evidence_artifacts": [
            {
                "artifact_id": r["artifact_id"],
                "content_hash": r["content_hash"],
                "provider": r["provider"],
                "tool": r["tool"],
                "ticker": r["ticker"],
                "retrieved_at": r["retrieved_at"].isoformat() if r.get("retrieved_at") else None,
                "cache_hit": r["cache_hit"],
                "payload_excerpt": r["payload_excerpt"],
                "payload_size": r["payload_size"],
            }
            for r in artifact_rows
        ],
        "citation_validation": (
            json.loads(validation_row["validation_data"])
            if validation_row and validation_row.get("validation_data")
            else None
        ),
        "analyses": [
            {
                "ticker": r["ticker"],
                "signal": r["signal"],
                "confidence": r["confidence"],
                "thesis": r["thesis"],
                "citations": json.loads(r["citations"]) if r.get("citations") else [],
                "data_gaps": json.loads(r["data_gaps"]) if r.get("data_gaps") else [],
            }
            for r in analysis_rows
        ],
        "integrity": {
            "artifact_count": len(artifact_rows),
            "bundle_hash": "",  # computed below
        },
    }

    # Compute bundle integrity hash (excludes the hash field itself)
    bundle_content = json.dumps(bundle, sort_keys=True, separators=(",", ":"), default=str)
    bundle["integrity"]["bundle_hash"] = hashlib.sha256(bundle_content.encode()).hexdigest()

    return bundle
