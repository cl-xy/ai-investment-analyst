"""
Lazy symbol resolver for non-US tickers.

When a bare symbol (e.g. VWRA) fails Yahoo Finance lookup, this module
uses yfinance's Search API to find the canonical suffixed symbol (VWRA.L).
Results are cached for 24h to avoid repeated resolution overhead.
"""

import logging
import queue
import threading

import yfinance as yf

from .cache import _symbol_cache

log = logging.getLogger(__name__)

_cache_lock = threading.Lock()

# yf.Search() has no session/timeout parameter (unlike yf.Lookup), so it can't
# inherit the timeout-enforcing session used elsewhere in this package. Run it
# in a dedicated daemon thread with a hard wall-clock timeout: if Search hangs,
# this call gives up promptly and the abandoned thread can't block interpreter
# shutdown or occupy the shared market_server _EXECUTOR pool.
_SEARCH_TIMEOUT = 10.0  # seconds


def _search_quotes(key: str, max_results: int, result_q: "queue.Queue") -> None:
    try:
        search = yf.Search(key, max_results=max_results)
        result_q.put(("ok", search.quotes if search.quotes else []))
    except Exception as e:
        result_q.put(("error", e))


def _search_with_timeout(key: str, max_results: int = 5, timeout: float = _SEARCH_TIMEOUT) -> list:
    """Run yf.Search with a hard timeout. Raises TimeoutError or the search's own exception."""
    result_q: "queue.Queue" = queue.Queue(maxsize=1)
    thread = threading.Thread(target=_search_quotes, args=(key, max_results, result_q), daemon=True)
    thread.start()
    try:
        status, payload = result_q.get(timeout=timeout)
    except queue.Empty:
        raise TimeoutError(f"yf.Search({key!r}) exceeded {timeout}s timeout") from None
    if status == "error":
        raise payload
    return payload


def resolve_symbol(bare_ticker: str) -> str | None:
    """
    Attempt to resolve a bare ticker to its Yahoo Finance canonical symbol.

    Returns the resolved symbol (e.g. VWRA.L) or None if resolution fails.
    Only called after the bare symbol has already failed a direct lookup.
    """
    key = bare_ticker.upper()

    # Check cache first
    with _cache_lock:
        if key in _symbol_cache:
            cached = _symbol_cache[key]
            log.debug("symbol_cache_hit bare=%s resolved=%s", key, cached)
            return cached

    # Skip resolution for symbols that already have an exchange suffix
    if "." in key and not key.endswith("."):
        return None

    try:
        quotes = _search_with_timeout(key, max_results=5)
    except Exception as e:
        log.warning("symbol_search_failed bare=%s error=%s", key, e)
        return None

    if not quotes:
        log.info("symbol_search_empty bare=%s", key)
        # Cache the miss to avoid repeated failed searches
        with _cache_lock:
            _symbol_cache[key] = None  # type: ignore[assignment]
        return None

    # Pick the top result that is marked as a Yahoo Finance symbol
    for quote in quotes:
        symbol = quote.get("symbol")
        is_yf = quote.get("isYahooFinance", False)
        if symbol and is_yf and symbol.upper() != key:
            resolved = symbol.upper()
            log.info(
                "symbol_resolved bare=%s resolved=%s exchange=%s",
                key,
                resolved,
                quote.get("exchDisp", "unknown"),
            )
            with _cache_lock:
                _symbol_cache[key] = resolved
            return resolved

    # All results matched the bare symbol or weren't usable
    with _cache_lock:
        _symbol_cache[key] = None  # type: ignore[assignment]
    return None
