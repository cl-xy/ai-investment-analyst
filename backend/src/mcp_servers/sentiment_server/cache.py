import threading
from typing import Any

from cachetools import TTLCache

# Short-lived dedupe cache (30s) to collapse burst requests within a single
# analysis run. Real freshness is owned by the PostgreSQL SWR cache layer in
# cache/manager.py which wraps all tool invocations in fetch_data_node.
#
# TTLCache is not thread-safe; all access is serialized through _lock.
# FastMCP sync tools run in a threadpool, so concurrent access is expected.
_sentiment_cache: TTLCache = TTLCache(maxsize=100, ttl=30)
_lock = threading.Lock()


def get_cached_sentiment(key: str) -> Any | None:
    """Return cached result for key, or None if not present/expired."""
    with _lock:
        return _sentiment_cache.get(key)


def set_cached_sentiment(key: str, value: Any) -> None:
    """Store a sentiment result under key."""
    with _lock:
        _sentiment_cache[key] = value
