from cachetools import TTLCache

# Short-lived dedupe caches (30s) to collapse burst requests within a single
# analysis run. Real freshness is owned by the PostgreSQL SWR cache layer in
# cache/manager.py which wraps all tool invocations in fetch_data_node.
_news_cache: TTLCache = TTLCache(maxsize=100, ttl=30)
_headlines_cache: TTLCache = TTLCache(maxsize=50, ttl=30)
