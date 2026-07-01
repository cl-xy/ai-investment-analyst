"""Utilities for robustly extracting JSON from LLM responses."""

import json
import re


def extract_json(text: str) -> dict | list:
    """
    Parse JSON from an LLM response, stripping markdown code fences if present.
    Raises json.JSONDecodeError if no valid JSON is found.
    """
    text = text.strip()
    # Strip ```json ... ``` or ``` ... ``` fences
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    return json.loads(text)
