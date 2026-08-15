"""
Audit Bundle API: export immutable evidence provenance per analysis run.

Provides a downloadable JSON bundle containing all evidence artifacts,
citation validation results, and integrity hashes for reproducibility.
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from src.evidence.registry import get_audit_bundle

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("/{run_id}")
async def get_run_audit_bundle(run_id: str) -> JSONResponse:
    """Export the complete audit bundle for an analysis run.

    Contains: run metadata, all evidence artifacts with content hashes,
    citation validation results, and a bundle-level integrity hash.
    """
    bundle = await get_audit_bundle(run_id)
    if bundle is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    return JSONResponse(
        content=bundle,
        headers={
            "Content-Disposition": f'attachment; filename="audit-{run_id}.json"',
            "X-Content-Type-Options": "nosniff",
        },
    )
