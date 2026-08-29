"""
Shared helpers for coercing asyncpg JSONB columns.

asyncpg does not auto-decode JSON/JSONB columns unless a type codec is
registered on the connection. Without that, JSONB columns come back as
raw JSON text (str) instead of list/dict. These helpers normalize either
shape into the expected Python type, so callers are safe regardless of
whether decoding already happened upstream.
"""

from __future__ import annotations

import json


def as_list(value) -> list:
    """Coerce an asyncpg JSONB value to a list. Returns [] on any decode failure."""
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value:
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except (json.JSONDecodeError, ValueError):
            return []
    return []


def as_dict(value) -> dict:
    """Coerce an asyncpg JSONB value to a dict. Returns {} on any decode failure."""
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value:
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except (json.JSONDecodeError, ValueError):
            return {}
    return {}
