"""
Shared numeric utilities for safe float handling and JSON serialization.

Centralizes NaN/Infinity defense to avoid duplication across persistence,
debate nodes, MCP servers, and tool wrappers.
"""

import json
import math


def safe_float(value, default: float = 0.0) -> float:
    """Convert value to a finite float, returning default on failure or non-finite.

    Handles None, strings, and edge cases from yfinance/Alpha Vantage responses.
    """
    if value is None:
        return default
    try:
        result = float(value)
    except (ValueError, TypeError):
        return default
    if not math.isfinite(result):
        return default
    return result


def safe_float_or_none(value) -> float | None:
    """Convert value to a finite float, returning None on failure.

    Preferred when the caller needs to distinguish missing data from zero.
    """
    if value is None:
        return None
    try:
        result = float(value)
    except (ValueError, TypeError):
        return None
    if not math.isfinite(result):
        return None
    return result


def sanitize_floats(obj):
    """Recursively replace NaN/Infinity float values with None for JSON safety."""
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    if isinstance(obj, dict):
        return {k: sanitize_floats(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [sanitize_floats(item) for item in obj]
    return obj


def safe_json_dumps(obj) -> str:
    """Serialize to JSON string, replacing NaN/Infinity with null.

    Falls back gracefully for non-serializable types via default=str.
    """
    if obj is None:
        return "null"
    try:
        return json.dumps(obj, allow_nan=False)
    except (TypeError, ValueError):
        # Sanitize non-finite floats and retry with default=str
        try:
            return json.dumps(sanitize_floats(obj), default=str, allow_nan=False)
        except (TypeError, ValueError):
            if isinstance(obj, list):
                return "[]"
            return "{}"
