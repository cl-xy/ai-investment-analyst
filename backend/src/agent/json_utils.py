"""Utilities for robustly extracting JSON from LLM responses."""

import json
import re

# Matches a fenced code block anywhere in the text (case-insensitive language tag)
_FENCE_RE = re.compile(r"```(?:json)?\s*\n?(.*?)\s*```", re.DOTALL | re.IGNORECASE)


def extract_json(text: str) -> dict | list:
    """
    Parse JSON from an LLM response, stripping markdown code fences if present.

    Handles prose-wrapped fenced blocks (e.g., "Here is the JSON: ```json ...```")
    and case variations of the language tag (json, JSON, Json).

    Raises:
        json.JSONDecodeError: if no valid JSON is found.
        ValueError: if parsed JSON is a scalar (not a dict or list).
    """
    text = text.strip()

    # Try to extract from a fenced code block anywhere in the response
    fenced = _FENCE_RE.search(text)
    if fenced:
        text = fenced.group(1).strip()

    result = json.loads(text)

    if not isinstance(result, (dict, list)):
        raise ValueError(f"Expected JSON object or array, got {type(result).__name__}")

    return result
