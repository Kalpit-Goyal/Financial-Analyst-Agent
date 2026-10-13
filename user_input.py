from functools import lru_cache
import yfinance as yf


@lru_cache(maxsize=256)
def search_tickers(query: str) -> tuple:
    try:
        quotes = yf.Search(query).quotes
    except Exception:
        return ()
    return tuple(
        {"symbol": q["symbol"], "name": q.get("shortname") or q.get("longname"), "exchange": q.get("exchDisp")}
        for q in quotes if q.get("quoteType") == "EQUITY"
    )[:5]


# Keep old get_ticker for backward compatibility (used by graph.py for now)
def get_ticker(state):
    company = state["company"]

    try:
        search = yf.Search(company)
        results = search.quotes
    except Exception as e:
        return {
            "ticker": "not available",
            "error": str(e),
        }

    if not results:
        return {
            "ticker": "not available",
        }

    for result in results:
        if result.get("quoteType") == "EQUITY":
            return {
                "ticker": result["symbol"],
            }

    return {
        "ticker": "not available",
    }