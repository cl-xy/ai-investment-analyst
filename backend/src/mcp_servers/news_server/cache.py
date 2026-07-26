from cachetools import TTLCache

# 60-minute TTL, news doesn't change that fast during a session
_news_cache: TTLCache = TTLCache(maxsize=500, ttl=3600)
_headlines_cache: TTLCache = TTLCache(maxsize=50, ttl=3600)
