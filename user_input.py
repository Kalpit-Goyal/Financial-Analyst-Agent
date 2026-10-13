import time
import yfinance as yf

# Simple dict cache: only store non-empty results to avoid caching failures
# Key is normalized to lowercase for case-insensitive matching
_search_cache: dict[str, tuple] = {}
_CACHE_TTL = 900  # 15 minutes
_MAX_CACHE_SIZE = 128


def _normalize_query(query: str) -> str:
    return query.strip().lower()


def _evict_expired(now: float):
    """Remove expired entries; if still over limit, remove oldest."""
    expired = [k for k, (ts, _) in _search_cache.items() if now - ts > _CACHE_TTL]
    for k in expired:
        _search_cache.pop(k, None)

    if len(_search_cache) > _MAX_CACHE_SIZE:
        # Remove oldest entries
        sorted_keys = sorted(_search_cache.keys(), key=lambda k: _search_cache[k][0])
        for k in sorted_keys[:len(_search_cache) - _MAX_CACHE_SIZE]:
            _search_cache.pop(k, None)


def search_tickers(query: str) -> tuple:
    """Search for equity tickers matching a query. Caches non-empty results only."""
    normalized = _normalize_query(query)
    now = time.monotonic()

    # Evict expired/old entries before checking cache
    _evict_expired(now)

    cached = _search_cache.get(normalized)
    if cached:
        ts, results = cached
        if now - ts < _CACHE_TTL:
            return results

    try:
        quotes = yf.Search(query).quotes
    except Exception:
        return ()

    results = tuple(
        {"symbol": q["symbol"], "name": q.get("shortname") or q.get("longname"), "exchange": q.get("exchDisp")}
        for q in quotes if q.get("quoteType") == "EQUITY"
    )[:5]

    if results:
        _search_cache[normalized] = (now, results)

    return results