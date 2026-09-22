from state import AgentState
import yfinance as yf


def get_ticker(state: AgentState) -> dict:
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
