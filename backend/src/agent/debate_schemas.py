"""
Pydantic schemas for the adversarial debate structured outputs.

Each debate agent (bull, bear, moderator) returns typed JSON validated here.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class DebateEvidence(BaseModel):
    """A single piece of cited evidence in a debate turn."""

    claim: str
    source_id: str
    provider: str = ""


class BullCaseOutput(BaseModel):
    """Structured output from the bull analyst agent."""

    ticker: str
    thesis: str = Field(description="2-3 sentence bullish thesis")
    key_arguments: list[str] = Field(default_factory=list, description="3-5 bullish arguments")
    catalysts: list[str] = Field(default_factory=list, description="Near-term catalysts")
    evidence: list[DebateEvidence] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low"] = "medium"
    acknowledged_risks: list[str] = Field(default_factory=list)


class BearRebuttal(BaseModel):
    """A structured rebuttal to a bull argument."""

    bull_claim: str
    counter: str


class BearCaseOutput(BaseModel):
    """Structured output from the bear analyst agent."""

    ticker: str
    thesis: str = Field(description="2-3 sentence bearish thesis")
    key_arguments: list[str] = Field(default_factory=list, description="3-5 bearish arguments")
    rebuttals: list[BearRebuttal] = Field(default_factory=list, description="Rebuttals to bull")
    risk_flags: list[str] = Field(default_factory=list)
    evidence: list[DebateEvidence] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low"] = "medium"
    conceded_strengths: list[str] = Field(default_factory=list)


class ModeratorOutput(BaseModel):
    """Structured output from the moderator/CIO agent. Maps to AnalysisOutput."""

    ticker: str
    signal: Literal["buy", "hold", "sell", "insufficient_data"]
    confidence: Literal["high", "medium", "low"]
    sentiment_score: float = Field(ge=-1.0, le=1.0)
    thesis: str = Field(description="Final investment thesis incorporating both sides")
    bull_case: list[str] = Field(default_factory=list)
    bear_case: list[str] = Field(default_factory=list)
    key_disagreements: list[str] = Field(default_factory=list)
    verdict_rationale: str = ""
    risk_flags: list[str] = Field(default_factory=list)
    citations: list[DebateEvidence] = Field(default_factory=list)
    data_gaps: list[str] = Field(default_factory=list)
    news_summary: str = ""
    sec_notes: str = ""


# Ordered role sequence for the adversarial debate protocol.
# Used by the streaming handler to map LLM completion index to role.
DEBATE_ROLES: list[str] = ["bull", "bear", "moderator"]


class DebateRecord(BaseModel):
    """Full debate transcript for persistence."""

    ticker: str
    bull: BullCaseOutput
    bear: BearCaseOutput
    moderator: ModeratorOutput
    model_name: str = "openai/gpt-oss-120b"
    prompt_version: str = "v1"
