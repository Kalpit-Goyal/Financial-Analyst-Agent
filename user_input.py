import time
import yfinance as yf

# Simple dict cache: only store non-empty results to avoid caching failures
_search_cache: dict[str, tuple] = {}
_CACHE_TTL = 900  # 15 minutes


def search_tickers(query: str) -> tuple:
    """Search for equity tickers matching a query. Caches non-empty results only."""
    now = time.monotonic()
    cached = _search_cache.get(query)
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
        _search_cache[query] = (now, results)

    return results