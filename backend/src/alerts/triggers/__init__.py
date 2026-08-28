"""
Event trigger monitors for the alert pipeline.

Each trigger module answers one narrow question — "did X change since the
last analysis?" — and returns a TriggerEvent (or None). trigger_manager.py
fans these out across tickers with bounded concurrency and aggregates the
results for the drift scorer.
"""
