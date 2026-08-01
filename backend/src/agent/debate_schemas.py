"""
Pydantic schemas for the adversarial debate structured outputs.

Each debate agent (bull, bear, moderator) returns typed JSON validated here.
"""

from __future__ import annotations

from typing import Annotated, Final, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, field_validator, model_validator


def _normalize_literal(v: object) -> object:
    """Lowercase and strip string values before Literal validation."""
    if isinstance(v, str):
        return v.strip().lower()
    return v


# Reusable annotated type for confidence fields across all debate models.
NormalizedConfidence = Annotated[
    Literal["high", "medium", "low"],
    BeforeValidator(_normalize_literal),
]


VALID_PROVIDERS: Final[tuple[str, ...]] = (
    "yfinance",
    "newsapi",
    "sec_edgar",
    "alpha_vantage",
    "rss",
    "stocktwits",
)


class DebateEvidence(BaseModel):
    """A single piece of cited evidence in a debate turn."""

    claim: str
    source_id: str
    provider: str = ""

    @field_validator("provider", mode="before")
    @classmethod
    def _sanitize_provider(cls, v: object) -> str:
        """Normalize provider to a known value or fall back to source_id prefix."""
        if not isinstance(v, str):
            return ""
        normalized = v.strip().lower().replace(" ", "_")
        if normalized in VALID_PROVIDERS:
            return normalized
        # LLM sometimes puts reasoning text here; extract known provider if embedded
        for p in VALID_PROVIDERS:
            if p in normalized:
                return p
        return ""


class BullCaseOutput(BaseModel):
    """Structured output from the bull analyst agent."""

    ticker: str
    thesis: str = Field(description="2-3 sentence bullish thesis")
    key_arguments: list[str] = Field(default_factory=list, description="3-5 bullish arguments")
    catalysts: list[str] = Field(default_factory=list, description="Near-term catalysts")
    evidence: list[DebateEvidence] = Field(default_factory=list)
    confidence: NormalizedConfidence = "medium"
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
    confidence: NormalizedConfidence = "medium"
    conceded_strengths: list[str] = Field(default_factory=list)


class ModeratorOutput(BaseModel):
    """Structured output from the moderator/CIO agent. Maps to AnalysisOutput."""

    ticker: str
    signal: Literal["buy", "hold", "sell", "insufficient_data"]
    confidence: NormalizedConfidence
    sentiment_score: float = Field(ge=-1.0, le=1.0, allow_inf_nan=False)
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

    @field_validator("signal", mode="before")
    @classmethod
    def _normalize_signal(cls, v: object) -> object:
        if isinstance(v, str):
            return v.strip().lower().replace(" ", "_")
        return v

    @field_validator("sentiment_score", mode="before")
    @classmethod
    def _clamp_sentiment(cls, v: object) -> object:
        """Clamp out-of-range LLM values to [-1.0, 1.0] instead of crashing.

        NaN and Infinity are passed through unclamped so that Pydantic's
        allow_inf_nan=False constraint rejects them with a clear error.
        """
        import math

        if isinstance(v, (int, float)):
            fv = float(v)
            if math.isnan(fv) or math.isinf(fv):
                return v  # let Field(allow_inf_nan=False) reject it
            return max(-1.0, min(1.0, fv))
        return v


# Ordered role sequence for the adversarial debate protocol.
# Used by the streaming handler to map LLM completion index to role.
DEBATE_ROLES: Final[tuple[str, ...]] = ("bull", "bear", "moderator")


class DebateRecord(BaseModel):
    """Full debate transcript for persistence."""

    model_config = ConfigDict(protected_namespaces=())

    ticker: str
    bull: BullCaseOutput
    bear: BearCaseOutput
    moderator: ModeratorOutput
    model_name: str = "nvidia/nemotron-3-super-120b-a12b:free"
    prompt_version: str = "v1"

    @model_validator(mode="after")
    def _check_ticker_consistency(self) -> DebateRecord:
        """Ensure nested tickers match the record-level ticker."""
        expected = self.ticker
        for role in ("bull", "bear", "moderator"):
            nested: BullCaseOutput | BearCaseOutput | ModeratorOutput = getattr(self, role)
            if nested.ticker and nested.ticker.upper() != expected.upper():
                # Correct silent ticker drift from LLM hallucination
                nested.ticker = expected
        return self
