"""
SEC filing trigger: detects a new 8-K/10-Q filed since the ticker's last
analysis. Uses the lightweight data probe (already fetched) rather than
hitting EDGAR again — the trigger's job is interpretation, not fetching.
"""

from __future__ import annotations

from src.alerts.data_probe import ProbeResult
from src.alerts.last_analysis import LastAnalysisSnapshot
from src.alerts.triggers.events import TriggerEvent


def check_sec_filing_trigger(
    snapshot: LastAnalysisSnapshot | None, probe: ProbeResult
) -> TriggerEvent | None:
    """Fire if the probe found a filing dated after the last analysis was run.

    If there's no prior analysis at all, we don't know what's "new" yet —
    skip rather than treating every filing as novel on first contact.
    """
    if snapshot is None:
        return None
    if not probe.latest_filing_date:
        return None

    last_analysis_date = snapshot.created_at.date().isoformat()
    if probe.latest_filing_date <= last_analysis_date:
        return None

    form = probe.latest_filing_form_type or "filing"
    return TriggerEvent(
        ticker=probe.ticker,
        trigger_type="sec_filing",
        summary=f"New {form} filed on {probe.latest_filing_date}",
        metadata={
            "filed_date": probe.latest_filing_date,
            "form_type": probe.latest_filing_form_type,
            "last_analysis_date": last_analysis_date,
        },
    )
