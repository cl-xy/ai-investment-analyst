"""
Reasoning-Aware Signal Alerts.

Detects when the underlying investment thesis for a monitored ticker has
materially changed (not just when price crosses a threshold) and notifies
the user via Telegram + an in-app alert feed.

Pipeline: triggers -> heuristic drift scorer -> (conditional) LLM drift judge
-> alert composer -> persistence + Telegram dispatch.
"""
