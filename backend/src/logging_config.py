"""
Structured JSON logging configuration.

Provides request-correlated, JSON-formatted logs for production observability.
Uses structlog for consistent structured output across the application.
"""

import logging
import sys
import uuid
from contextvars import ContextVar

import structlog

# Context variable for request correlation
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="")


def get_request_id() -> str:
    """Get the current request's correlation ID."""
    return request_id_ctx.get()


def _add_request_id(logger, method_name, event_dict):
    """Processor that adds request_id to all log entries."""
    rid = request_id_ctx.get()
    if rid:
        event_dict["request_id"] = rid
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
        _add_request_id,
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
