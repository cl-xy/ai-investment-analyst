"""
Shared TriggerEvent type returned by every trigger module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

TriggerType = Literal["sec_filing", "sentiment", "peer_signal", "price"]


@dataclass(frozen=True, slots=True)
class TriggerEvent:
    """A single fired trigger for one ticker. Carries just enough metadata
    for the composer to explain *why* an alert fired, without duplicating
    the full drift score computation (that's drift_scorer's job)."""

    ticker: str
    trigger_type: TriggerType
    summary: str
    metadata: dict = field(default_factory=dict)
