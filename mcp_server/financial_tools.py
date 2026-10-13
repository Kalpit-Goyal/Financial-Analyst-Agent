import asyncio
import math
import os
import re
import time
from datetime import date, datetime
from typing import Literal

import numpy as np
import pandas as pd
import yfinance as yf
from mcp.server.fastmcp import FastMCP
from yfinance.exceptions import YFRateLimitError

mcp = FastMCP("FinancialTools")

PERIOD_LIMIT = int(os.getenv("FIN_TOOL_PERIODS", "8"))
CACHE_TTL = int(os.getenv("FIN_TOOL_CACHE_TTL", "900"))
CURRENCY_CACHE_TTL = int(os.getenv("FIN_TOOL_CURRENCY_CACHE_TTL", "60"))
RETRY_BACKOFF = float(os.getenv("FIN_TOOL_RETRY_BACKOFF", "3"))
MAX_CACHE_SIZE = 256

TICKER_REGEX = re.compile(r"^[A-Za-z0-9.\-^=]{1,15}$")

_cache: dict = {}
_currency_cache: dict = {}


def _cache_get(key):
    entry = _cache.get(key)
    if entry is None:
        return None
    stored_at, value = entry
    if time.monotonic() - stored_at > CACHE_TTL:
        _cache.pop(key, None)
        return None
    return value


def _cache_set(key, value):
    _cache[key] = (time.monotonic(), value)
    if len(_cache) > MAX_CACHE_SIZE:
        now = time.monotonic()
        expired = [k for k, (ts, _) in _cache.items() if now - ts > CACHE_TTL]
        for k in expired:
            _cache.pop(k, None)


def _cached(key, loader):
    hit = _cache_get(key)
    if hit is not None:
        return {**hit, "cached": True}

    result = loader()
    if "error" not in result:
        _cache_set(key, result)
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


def _get_currency(ticker: str) -> str | None:
    """Get and cache the financial currency for a ticker."""
    now = time.monotonic()
    if ticker in _currency_cache:
        ts, curr = _currency_cache[ticker]
        if now - ts < CURRENCY_CACHE_TTL:
            return curr

    try:
        info = yf.Ticker(ticker).get_info()
        if isinstance(info, dict):
            currency = info.get("financialCurrency") or info.get("currency")
            if currency:
                _currency_cache[ticker] = (now, currency)
                return currency
    except Exception:
        pass
    # Cache failure for CURRENCY_CACHE_TTL seconds to avoid hammering on rate limits
    _currency_cache[ticker] = (now, None)
    return None


def _statement(ticker: str, frame: pd.DataFrame, source: str, frequency: str, currency: str | None = None):
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return {
            "ticker": ticker,
            "source": source,
            "frequency": frequency,
            "periods": [],
            "data": {},
            "currency": currency,
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
        "currency": currency,
    }


def _with_rate_limit_retry(ticker: str, source: str, loader):
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


def _market_data(ticker: str, stock: yf.Ticker) -> dict:
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
        info = _with_rate_limit_retry(ticker, "market data", lambda: stock.get_info())
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


def _validate_ticker(ticker: str) -> dict | None:
    if not TICKER_REGEX.match(ticker):
        return {
            "ticker": ticker,
            "error": f"Invalid ticker format: {ticker}",
            "retryable": False,
            "advice": "Provide a valid ticker symbol (e.g., NVDA, AAPL, MSFT).",
        }
    return None


def _get_financials_sync(ticker: str, period: Literal["annual", "quarterly"]) -> dict:
    """Synchronous inner function for get_financials."""
    frequency = "quarterly" if period == "quarterly" else "annual"
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

    currency = _get_currency(ticker)
    result = _cached((f"income_stmt_{frequency}", ticker), loader)
    if "error" not in result:
        result["currency"] = currency
    return result


@mcp.tool()
async def get_financials(ticker: str, period: Literal["annual", "quarterly"] = "annual") -> dict:
    """Get the company's income statement from Yahoo Finance: revenue, cost of
    revenue, gross profit, operating income, net income and margins.

    Set period="quarterly" for quarter-by-quarter data or period="annual" for
    full-year figures. Check the "frequency", "periods", and "currency" fields
    in the result before reporting a figure, and always state the period and
    currency the number covers.
    """
    err = _validate_ticker(ticker)
    if err:
        return err

    try:
        return await asyncio.to_thread(_get_financials_sync, ticker, period)
    except Exception as exc:
        return {
            "ticker": ticker,
            "error": f"{type(exc).__name__}: {exc}",
            "retryable": False,
            "advice": "Report this data as unavailable. Do not retry.",
        }


def _get_balance_sheet_sync(ticker: str, period: Literal["annual", "quarterly"]) -> dict:
    """Synchronous inner function for get_balance_sheet."""
    frequency = "quarterly" if period == "quarterly" else "annual"
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

    currency = _get_currency(ticker)
    result = _cached((f"balance_sheet_{frequency}", ticker), loader)
    if "error" not in result:
        result["currency"] = currency
    return result


@mcp.tool()
async def get_balance_sheet(ticker: str, period: Literal["annual", "quarterly"] = "annual") -> dict:
    """Get the company's balance sheet from Yahoo Finance: total assets, total
    liabilities, cash, total debt and shareholders equity.

    Set period="quarterly" for quarter-by-quarter data or period="annual" for
    full-year figures. Check the "frequency", "periods", and "currency" fields
    in the result before reporting a figure.
    """
    err = _validate_ticker(ticker)
    if err:
        return err

    try:
        return await asyncio.to_thread(_get_balance_sheet_sync, ticker, period)
    except Exception as exc:
        return {
            "ticker": ticker,
            "error": f"{type(exc).__name__}: {exc}",
            "retryable": False,
            "advice": "Report this data as unavailable. Do not retry.",
        }


def _get_cash_flow_sync(ticker: str, period: Literal["annual", "quarterly"]) -> dict:
    """Synchronous inner function for get_cash_flow."""
    frequency = "quarterly" if period == "quarterly" else "annual"
    attribute = "quarterly_cash_flow" if frequency == "quarterly" else "cash_flow"

    def loader():
        return _with_rate_limit_retry(
            ticker,
            f"{attribute} (cash flow)",
            lambda: _statement(
                ticker,
                getattr(yf.Ticker(ticker), attribute),
                f"cash_flow_{frequency}",
                frequency,
            ),
        )

    currency = _get_currency(ticker)
    result = _cached((f"cash_flow_{frequency}", ticker), loader)
    if "error" not in result:
        result["currency"] = currency
    return result


@mcp.tool()
async def get_cash_flow(ticker: str, period: Literal["annual", "quarterly"] = "annual") -> dict:
    """Get the company's cash flow statement from Yahoo Finance: operating cash flow,
    investing cash flow, financing cash flow, and free cash flow.

    Set period="quarterly" for quarter-by-quarter data or period="annual" for
    full-year figures. Check the "frequency", "periods", and "currency" fields
    in the result before reporting a figure.
    """
    err = _validate_ticker(ticker)
    if err:
        return err

    try:
        return await asyncio.to_thread(_get_cash_flow_sync, ticker, period)
    except Exception as exc:
        return {
            "ticker": ticker,
            "error": f"{type(exc).__name__}: {exc}",
            "retryable": False,
            "advice": "Report this data as unavailable. Do not retry.",
        }


def _get_market_data_sync(ticker: str) -> dict:
    """Synchronous inner function for get_market_data."""
    def loader():
        return _with_rate_limit_retry(
            ticker,
            "market data",
            lambda: _market_data(ticker, yf.Ticker(ticker)),
        )

    result = _cached(("market_data", ticker), loader)
    return result


@mcp.tool()
async def get_market_data(ticker: str) -> dict:
    """Get the company's current market and valuation data from Yahoo Finance:
    share price, market cap, 52-week range, average volume and valuation
    multiples such as P/E, EV/EBITDA and price/sales."""
    err = _validate_ticker(ticker)
    if err:
        return err

    try:
        return await asyncio.to_thread(_get_market_data_sync, ticker)
    except Exception as exc:
        return {
            "ticker": ticker,
            "error": f"{type(exc).__name__}: {exc}",
            "retryable": False,
            "advice": "Report this data as unavailable. Do not retry.",
        }


if __name__ == "__main__":
    transport = os.getenv("MCP_TRANSPORT", "stdio")
    if transport == "stdio":
        mcp.run()
    else:
        mcp.settings.host = os.getenv("MCP_HOST", "127.0.0.1")
        mcp.settings.port = int(os.getenv("MCP_PORT", "8931"))
        mcp.run(transport=transport)