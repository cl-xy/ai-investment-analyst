"""
Structured JSON logging configuration.

Provides request-correlated, JSON-formatted logs for production observability.
Uses structlog for consistent structured output across the application.
"""

import logging
import re
import sys
import time
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

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


def get_request_id() -> str:
    """Get the current request's correlation ID."""
    return request_id_ctx.get()


def bind_context(
    *,
    ticker: str | None = None,
    run_id: str | None = None,
    node_name: str | None = None,
) -> None:
    """Bind domain correlation fields to the current async context."""
    if ticker is not None:
        ticker_ctx.set(ticker)
    if run_id is not None:
        run_id_ctx.set(run_id)
    if node_name is not None:
        node_name_ctx.set(node_name)


def clear_context() -> None:
    """Clear all domain correlation fields."""
    ticker_ctx.set("")
    run_id_ctx.set("")
    node_name_ctx.set("")


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
            val = event_dict[key]
            if key in ("value", "header") and _SENSITIVE_PATTERN.search(str(event_dict.get("event", ""))):
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


def log_event(event: str, **fields: Any) -> None:
    """
    Log a structured domain event with automatic correlation context.

    Usage:
        log_event("tool_call_completed", tool="get_quote", ticker="NVDA", cached=True, duration_ms=45)
    """
    logger = structlog.get_logger("domain")
    logger.info(event, **fields)


@contextmanager
def timed(operation: str, **extra_fields: Any):
    """
    Context manager that measures and logs operation duration.

    Usage:
        with timed("fetch_quote", ticker="AAPL"):
            result = await get_quote("AAPL")
    """
    logger = structlog.get_logger("timing")
    start = time.monotonic()
    try:
        yield
    except Exception as exc:
        duration_ms = round((time.monotonic() - start) * 1000, 1)
        logger.error(
            f"{operation}_failed",
            duration_ms=duration_ms,
            error=str(exc),
            **extra_fields,
        )
        raise
    else:
        duration_ms = round((time.monotonic() - start) * 1000, 1)
        logger.info(
            f"{operation}_completed",
            duration_ms=duration_ms,
            **extra_fields,
        )
