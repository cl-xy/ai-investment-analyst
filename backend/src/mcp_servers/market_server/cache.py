from cachetools import TTLCache

# 15-minute TTL caches, shared across the server process lifetime
_quote_cache: TTLCache = TTLCache(maxsize=500, ttl=900)
_fundamentals_cache: TTLCache = TTLCache(maxsize=500, ttl=900)
_history_cache: TTLCache = TTLCache(maxsize=200, ttl=900)
