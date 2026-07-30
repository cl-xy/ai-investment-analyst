import threading

from cachetools import TTLCache

# Short-lived dedupe caches (30s) to collapse burst requests within a single
# analysis run. Real freshness is owned by the PostgreSQL SWR cache layer in
# cache/manager.py which wraps all tool invocations in fetch_data_node.
#
# TTLCache is not thread-safe, and FastMCP dispatches sync tool handlers via
# a thread pool, so we guard each cache with a lock.
_news_cache: TTLCache = TTLCache(maxsize=100, ttl=30)
_news_lock = threading.Lock()

_headlines_cache: TTLCache = TTLCache(maxsize=50, ttl=30)
_headlines_lock = threading.Lock()
