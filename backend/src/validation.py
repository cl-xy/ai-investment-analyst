"""
Shared input validation utilities.

Centralizes ticker symbol validation to avoid regex duplication across MCP
servers and API routes. Import from here instead of defining per-module.
"""

import re

# Accepts letters, digits, dots, hyphens. Max 12 chars covers crypto symbols
# like BTC.X and extended tickers like BRK-B. Case-insensitive via normalization.
TICKER_RE = re.compile(r"^[A-Za-z0-9.\-]{1,12}$")


def validate_ticker(ticker: str) -> str:
    """Normalize and validate a ticker symbol.

    Returns the uppercased, stripped ticker. Raises ValueError if invalid.
    """
    if not isinstance(ticker, str) or not ticker.strip():
        raise ValueError(f"Invalid ticker: {ticker!r}")
    normalized = ticker.strip().upper()
    if not TICKER_RE.fullmatch(normalized):
        raise ValueError(f"Invalid ticker format: {ticker!r}")
    return normalized


def validate_ticker_or_none(ticker: str) -> str | None:
    """Validate ticker, returning None instead of raising on failure.

    Useful for MCP tool handlers where invalid input should return empty results
    rather than crash the entire analysis pipeline.
    """
    try:
        return validate_ticker(ticker)
    except (ValueError, TypeError):
        return None
