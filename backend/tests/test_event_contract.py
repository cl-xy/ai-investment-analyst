"""
Contract test: verify frontend event type strings match backend EventType enum.

Prevents silent drift where backend adds/renames an event type and the frontend
EventSource listeners silently ignore the new type (no compile-time signal).
"""

from pathlib import Path

from src.agent.events import EventType


def test_frontend_event_types_match_backend():
    """Frontend hardcoded event type strings must be a superset of backend EventType values."""
    # Read the frontend hook that registers EventSource listeners
    frontend_hook = (
        Path(__file__).parent.parent.parent
        / "frontend"
        / "src"
        / "hooks"
        / "useAnalysisStream.ts"
    )
    assert frontend_hook.exists(), f"Frontend hook not found at {frontend_hook}"

    content = frontend_hook.read_text()

    # Extract the event types array from the frontend
    # Pattern: const eventTypes = ['type1', 'type2', ...]
    import re

    match = re.search(r"const eventTypes\s*=\s*\[(.*?)\]", content, re.DOTALL)
    assert match, "Could not find eventTypes array in useAnalysisStream.ts"

    raw = match.group(1)
    frontend_types = set(re.findall(r"'([^']+)'", raw))

    # Get all backend event type values
    backend_types = {e.value for e in EventType}

    # Frontend must handle all backend event types
    missing = backend_types - frontend_types
    assert not missing, (
        f"Backend event types not registered in frontend EventSource listeners: {missing}. "
        f"Add these to the eventTypes array in useAnalysisStream.ts."
    )
