import json

import yfinance as yf
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("FinancialTools")


def _sanitize(data):
    try:
        return json.loads(json.dumps(data, default=str))
    except (TypeError, ValueError):
        return {"error": "Failed to serialize financial data"}


@mcp.tool()
def get_financials(ticker: str) -> dict:
    """Get Company's Income Statement From Yahoo Finance"""

    try:
        stock = yf.Ticker(ticker)
        income = stock.income_stmt
        if hasattr(income, "dropna"):
            income = income.dropna(how="all")
        return _sanitize(income.to_dict())
    except Exception as e:
        return {"error": str(e), "ticker": ticker}


@mcp.tool()
def get_balance_sheet(ticker: str) -> dict:
    """Get the company's balance sheet from Yahoo Finance."""

    try:
        stock = yf.Ticker(ticker)
        balance = stock.balance_sheet
        if hasattr(balance, "dropna"):
            balance = balance.dropna(how="all")
        return _sanitize(balance.to_dict())
    except Exception as e:
        return {"error": str(e), "ticker": ticker}


@mcp.tool()
def get_market_data(ticker: str) -> dict:
    """Get the company's current market and valuation data from Yahoo Finance."""

    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        if isinstance(info, dict):
            info = dict(list(info.items())[:500])
        return _sanitize(info)
    except Exception as e:
        return {"error": str(e), "ticker": ticker}


if __name__ == "__main__":
    mcp.run()
