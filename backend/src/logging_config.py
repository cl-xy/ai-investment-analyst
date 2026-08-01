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

# Sensitive key names (exact match, case-insensitive).
# Uses word boundaries to avoid false positives on e.g. "max_tokens", "token_count".
_SENSITIVE_PATTERN = re.compile(
    r"(?:^|_|-)(api_key|password|passwd|token|authorization|secret|credential|private_key|access_key|session_id|cookie)(?:$|_|-)",
    re.IGNORECASE,
)
# Allowlist: keys that match the pattern but are known safe
_SENSITIVE_ALLOWLIST = frozenset(
    {"max_tokens", "token_count", "tokens_used", "total_tokens", "token_usage"}
)
_REDACTED = "[REDACTED]"
_MAX_REDACT_DEPTH = 5


def _is_sensitive_key(key: str) -> bool:
    """Check if a key name indicates sensitive content."""
    key_lower = key.lower()
    if key_lower in _SENSITIVE_ALLOWLIST:
        return False
    return bool(_SENSITIVE_PATTERN.search(key_lower))


def _redact_value(value, depth: int = 0):
    """Recursively redact sensitive fields in nested structures."""
    if depth > _MAX_REDACT_DEPTH:
        return value
    if isinstance(value, dict):
        return {
            k: _REDACTED
            if isinstance(k, str) and _is_sensitive_key(k)
            else _redact_value(v, depth + 1)
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        redacted = [_redact_value(item, depth + 1) for item in value]
        return type(value)(redacted)
    return value


def _add_correlation_fields(logger, method_name, event_dict):
    """Processor that adds all correlation fields to log entries."""
    rid = request_id_ctx.get()
    if rid:
        event_dict.setdefault("request_id", rid)

    ticker = ticker_ctx.get()
    if ticker:
        event_dict.setdefault("ticker", ticker)

    run_id = run_id_ctx.get()
    if run_id:
        event_dict.setdefault("run_id", run_id)

    node = node_name_ctx.get()
    if node:
        event_dict.setdefault("node_name", node)

    return event_dict


def _redact_sensitive(logger, method_name, event_dict):
    """Processor that redacts sensitive fields from log output (recursive)."""
    for key in list(event_dict.keys()):
        # Guard against non-string keys
        if not isinstance(key, str):
            continue
        if _is_sensitive_key(key):
            event_dict[key] = _REDACTED
        else:
            # Recursively redact nested structures
            value = event_dict[key]
            if isinstance(value, dict):
                event_dict[key] = _redact_value(value)
            elif isinstance(value, (list, tuple)):
                event_dict[key] = _redact_value(value)
    return event_dict


_VALID_LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})


def setup_logging(json_output: bool = True, level: str = "INFO"):
    """
    Configure structured logging for the application.

    Args:
        json_output: If True, emit JSON lines. If False, emit human-readable (dev mode).
        level: Minimum log level.

    Raises:
        ValueError: If level is not a valid log level name.
    """
    level_upper = level.upper()
    if level_upper not in _VALID_LOG_LEVELS:
        raise ValueError(
            f"Invalid log level: {level!r}. Must be one of: {sorted(_VALID_LOG_LEVELS)}"
        )

    shared_processors = [
        structlog.contextvars.merge_contextvars,
        _add_correlation_fields,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        # Redaction runs last before rendering so it catches exception text too
        _redact_sensitive,
    ]

    if json_output:
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[
            *shared_processors,  # type: ignore[list-item]
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, level_upper)),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = ""):
    """Get a structured logger instance with an identifiable name."""
    if name:
        return structlog.get_logger(name).bind(logger_name=name)
    return structlog.get_logger()
