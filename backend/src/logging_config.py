"""
Structured JSON logging configuration.

Provides request-correlated, JSON-formatted logs for production observability.
Uses structlog for consistent structured output across the application.
"""

import logging
import re
import sys
from contextvars import ContextVar

import structlog

# Context variables for request and domain correlation
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="")
ticker_ctx: ContextVar[str] = ContextVar("ticker", default="")
run_id_ctx: ContextVar[str] = ContextVar("run_id", default="")
node_name_ctx: ContextVar[str] = ContextVar("node_name", default="")

# Fields that should never appear in logs
_SENSITIVE_PATTERN = re.compile(
    r"(api_key|password|token|authorization|secret|credential)",
    re.IGNORECASE,
)
_REDACTED = "[REDACTED]"


def _add_correlation_fields(logger, method_name, event_dict):
    """Processor that adds all correlation fields to log entries."""
    rid = request_id_ctx.get()
    if rid:
        event_dict["request_id"] = rid

    ticker = ticker_ctx.get()
    if ticker:
        event_dict["ticker"] = ticker

    run_id = run_id_ctx.get()
    if run_id:
        event_dict["run_id"] = run_id

    node = node_name_ctx.get()
    if node:
        event_dict["node_name"] = node

    return event_dict


def _redact_sensitive(logger, method_name, event_dict):
    """Processor that redacts sensitive fields from log output."""
    for key in list(event_dict.keys()):
        if _SENSITIVE_PATTERN.search(key):
            event_dict[key] = _REDACTED
        elif isinstance(event_dict[key], str) and len(event_dict[key]) > 20:
            # Redact values that look like tokens/keys (long strings in known patterns)
            if key in ("value", "header") and _SENSITIVE_PATTERN.search(
                str(event_dict.get("event", ""))
            ):
                event_dict[key] = _REDACTED
    return event_dict


def setup_logging(json_output: bool = True, level: str = "INFO"):
    """
    Configure structured logging for the application.

    Args:
        json_output: If True, emit JSON lines. If False, emit human-readable (dev mode).
        level: Minimum log level.
    """
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        _add_correlation_fields,
        _redact_sensitive,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    if json_output:
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = ""):
    """Get a structured logger instance."""
    return structlog.get_logger(name)
