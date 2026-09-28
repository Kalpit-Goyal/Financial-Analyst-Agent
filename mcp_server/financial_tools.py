import math
import os
import time
from datetime import date, datetime

import numpy as np
import pandas as pd
import yfinance as yf
from mcp.server.fastmcp import FastMCP
from yfinance.exceptions import YFRateLimitError

mcp = FastMCP("FinancialTools")

PERIOD_LIMIT = int(os.getenv("FIN_TOOL_PERIODS", "8"))
CACHE_TTL = int(os.getenv("FIN_TOOL_CACHE_TTL", "900"))
RETRY_BACKOFF = float(os.getenv("FIN_TOOL_RETRY_BACKOFF", "3"))

_cache: dict = {}


def _cache_get(key):
    entry = _cache.get(key)
    if entry is None:
        return None
    stored_at, value = entry
    if time.monotonic() - stored_at > CACHE_TTL:
        _cache.pop(key, None)
        return None
    return value


def _cached(key, loader):
    hit = _cache_get(key)
    if hit is not None:
        return {**hit, "cached": True}

    result = loader()
    if "error" not in result:
        _cache[key] = (time.monotonic(), result)
    return result


def _json_key(key):
    if isinstance(key, (pd.Timestamp, datetime)):
        return key.date().isoformat()
    if isinstance(key, date):
        return key.isoformat()
    return str(key)


def _json_safe(obj):
    if obj is pd.NaT:
        return None
    if isinstance(obj, dict):
        return {_json_key(k): _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, (bool, np.bool_)):
        return bool(obj)
    if isinstance(obj, str) or obj is None:
        return obj
    if isinstance(obj, (int, np.integer)):
        return int(obj)
    if isinstance(obj, (float, np.floating)):
        value = float(obj)
        if math.isnan(value) or math.isinf(value):
            return None
        return value
    if isinstance(obj, (pd.Timestamp, datetime)):
        return obj.date().isoformat()
    if isinstance(obj, date):
        return obj.isoformat()
    return str(obj)


def _statement(ticker, frame, source, frequency):
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return {
            "ticker": ticker,
            "source": source,
            "frequency": frequency,
            "periods": [],
            "data": {},
            "note": f"Yahoo Finance returned no {source.replace('_', ' ')} data.",
        }

    frame = frame.dropna(how="all")
    frame = frame.loc[~frame.index.duplicated(keep="first")]
    frame = frame.iloc[:, :PERIOD_LIMIT]
    frame = frame.dropna(how="all", axis=1)

    return {
        "ticker": ticker,
        "source": source,
        "frequency": frequency,
        "periods": [_json_key(column) for column in frame.columns],
        "data": _json_safe(frame.to_dict()),
    }


def _with_rate_limit_retry(ticker, source, loader):
    for attempt in range(2):
        try:
            return loader()
        except YFRateLimitError as exc:
            if attempt == 0:
                time.sleep(RETRY_BACKOFF)
                continue
            return {
                "ticker": ticker,
                "error": f"Yahoo Finance rate limit hit while fetching {source}: {exc}",
                "retryable": False,
                "advice": (
                    "Yahoo Finance is rate limiting this request. Do not call this "
                    "tool again in this conversation. Tell the user that live "
                    "financial data is temporarily unavailable and suggest "
                    "retrying in a few minutes."
                ),
            }


FAST_INFO_FIELDS = {
    "lastPrice": "currentPrice",
    "previousClose": "previousClose",
    "currency": "currency",
    "marketCap": "marketCap",
    "yearHigh": "fiftyTwoWeekHigh",
    "yearLow": "fiftyTwoWeekLow",
    "tenDayAverageVolume": "tenDayAverageVolume",
    "threeMonthAverageVolume": "threeMonthAverageVolume",
    "shares": "sharesOutstanding",
    "exchange": "exchange",
}

INFO_FALLBACK_FIELDS = (
    "sector",
    "industry",
    "longName",
    "trailingPE",
    "forwardPE",
    "priceToSalesTrailing12Months",
    "priceToBook",
    "enterpriseToEbitda",
    "enterpriseToRevenue",
    "trailingEps",
    "forwardEps",
    "returnOnEquity",
    "profitMargins",
    "grossMargins",
    "dividendYield",
    "beta",
)


def _market_data(ticker, stock):
    snapshot = {"ticker": ticker, "source": "market_data"}

    try:
        fast = dict(stock.fast_info or {})
        for key, alias in FAST_INFO_FIELDS.items():
            if key in fast:
                snapshot[alias] = _json_safe(fast[key])
    except Exception as exc:
        snapshot["market_data_warning"] = str(exc)

    measures = None
    try:
        measures = stock.get_valuation_measures()
    except Exception as exc:
        snapshot["valuation_warning"] = str(exc)

    if isinstance(measures, pd.DataFrame) and not measures.empty:
        valuation = _json_safe(measures.to_dict())
    elif isinstance(measures, pd.Series) and not measures.empty:
        valuation = _json_safe(measures.to_dict())
    elif isinstance(measures, dict) and measures:
        valuation = _json_safe(measures)
    else:
        valuation = {}

    if valuation:
        snapshot["valuation"] = valuation
    else:
        info = _with_rate_limit_retry(ticker, "market data", stock.get_info)
        if isinstance(info, dict) and "error" not in info:
            snapshot["valuation"] = {
                field: _json_safe(info[field])
                for field in INFO_FALLBACK_FIELDS
                if field in info
            }
            snapshot["valuation_source"] = "info_fallback"
        else:
            snapshot["valuation"] = {}
            if isinstance(info, dict):
                snapshot["valuation_error"] = info.get("error")

    return snapshot


@mcp.tool()
def get_financials(ticker: str, period: str = "annual") -> dict:
    """Get the company's income statement from Yahoo Finance: revenue, cost of
    revenue, gross profit, operating income, net income and margins.

    Set period="quarterly" for quarter-by-quarter data or period="annual" for
    full-year figures. Check the "frequency" and "periods" fields in the result
    before reporting a figure, and always state the period the number covers.
    """

    frequency = "quarterly" if str(period).lower().startswith("q") else "annual"
    attribute = "quarterly_income_stmt" if frequency == "quarterly" else "income_stmt"
    label = f"{attribute} (income statement)"

    def loader():
        return _with_rate_limit_retry(
            ticker,
            label,
            lambda: _statement(
                ticker,
                getattr(yf.Ticker(ticker), attribute),
                f"income_stmt_{frequency}",
                frequency,
            ),
        )

    return _cached((f"income_stmt_{frequency}", ticker), loader)


@mcp.tool()
def get_balance_sheet(ticker: str, period: str = "annual") -> dict:
    """Get the company's balance sheet from Yahoo Finance: total assets, total
    liabilities, cash, total debt and shareholders equity.

    Set period="quarterly" for quarter-by-quarter data or period="annual" for
    full-year figures. Check the "frequency" and "periods" fields in the result
    before reporting a figure.
    """

    frequency = "quarterly" if str(period).lower().startswith("q") else "annual"
    attribute = "quarterly_balance_sheet" if frequency == "quarterly" else "balance_sheet"

    def loader():
        return _with_rate_limit_retry(
            ticker,
            f"{attribute} (balance sheet)",
            lambda: _statement(
                ticker,
                getattr(yf.Ticker(ticker), attribute),
                f"balance_sheet_{frequency}",
                frequency,
            ),
        )

    return _cached((f"balance_sheet_{frequency}", ticker), loader)


@mcp.tool()
def get_market_data(ticker: str) -> dict:
    """Get the company's current market and valuation data from Yahoo Finance:
    share price, market cap, 52-week range, average volume and valuation
    multiples such as P/E, EV/EBITDA and price/sales."""

    def loader():
        return _with_rate_limit_retry(
            ticker,
            "market data",
            lambda: _market_data(ticker, yf.Ticker(ticker)),
        )

    return _cached(("market_data", ticker), loader)


if __name__ == "__main__":
    transport = os.getenv("MCP_TRANSPORT", "stdio")
    if transport == "stdio":
        mcp.run()
    else:
        mcp.settings.host = os.getenv("MCP_HOST", "127.0.0.1")
        mcp.settings.port = int(os.getenv("MCP_PORT", "8931"))
        mcp.run(transport=transport)
