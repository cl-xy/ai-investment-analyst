from cachetools import TTLCache

# Short-lived dedupe caches (30s) to collapse burst requests within a single
# analysis run. Real freshness is owned by the PostgreSQL SWR cache layer in
# cache/manager.py which wraps all tool invocations in fetch_data_node.
_quote_cache: TTLCache = TTLCache(maxsize=100, ttl=30)
_fundamentals_cache: TTLCache = TTLCache(maxsize=100, ttl=30)
_history_cache: TTLCache = TTLCache(maxsize=100, ttl=30)
# Earnings dates rarely change day to day; dedupe longer than the others.
_earnings_cache: TTLCache = TTLCache(maxsize=100, ttl=300)
