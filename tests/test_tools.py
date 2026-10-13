import pytest
import json
import math
import asyncio
from datetime import date
from unittest.mock import patch, MagicMock, AsyncMock

import numpy as np
import pandas as pd

# Import modules under test
import mcp_server.financial_tools as ft
from mcp_server.financial_tools import (
    _json_key,
    _json_safe,
    _statement,
    _cached,
    _validate_ticker,
)
from state import AgentState, create_initial_state
from user_input import search_tickers


class TestJsonKey:
    def test_pd_timestamp(self):
        ts = pd.Timestamp("2024-01-15")
        assert _json_key(ts) == "2024-01-15"

    def test_datetime(self):
        from datetime import datetime
        dt = datetime(2024, 1, 15, 10, 30)
        assert _json_key(dt) == "2024-01-15"

    def test_date(self):
        d = date(2024, 1, 15)
        assert _json_key(d) == "2024-01-15"

    def test_string(self):
        assert _json_key("hello") == "hello"

    def test_int(self):
        assert _json_key(42) == "42"


class TestJsonSafe:
    def test_nan(self):
        assert _json_safe(float("nan")) is None

    def test_inf(self):
        assert _json_safe(float("inf")) is None
        assert _json_safe(float("-inf")) is None

    def test_numpy_int(self):
        assert _json_safe(np.int64(42)) == 42

    def test_numpy_float(self):
        assert _json_safe(np.float64(3.14)) == 3.14

    def test_numpy_bool(self):
        assert _json_safe(np.bool_(True)) is True

    def test_pd_timestamp(self):
        ts = pd.Timestamp("2024-01-15")
        assert _json_safe(ts) == "2024-01-15"

    def test_pd_nat(self):
        assert _json_safe(pd.NaT) is None

    def test_dict(self):
        result = _json_safe({"a": 1, "b": float("nan")})
        assert result == {"a": 1, "b": None}

    def test_list(self):
        result = _json_safe([1, float("nan"), "hello"])
        assert result == [1, None, "hello"]

    def test_none(self):
        assert _json_safe(None) is None

    def test_string(self):
        assert _json_safe("hello") == "hello"

    def test_int(self):
        assert _json_safe(42) == 42

    def test_float(self):
        assert _json_safe(3.14) == 3.14

    def test_bool(self):
        assert _json_safe(True) is True


class TestStatement:
    def test_empty_frame(self):
        df = pd.DataFrame()
        result = _statement("NVDA", df, "income_stmt_annual", "annual")
        assert result["ticker"] == "NVDA"
        assert result["source"] == "income_stmt_annual"
        assert result["frequency"] == "annual"
        assert result["periods"] == []
        assert result["data"] == {}
        assert "Yahoo Finance returned no income stmt annual data" in result["note"]

    def test_frame_with_data(self):
        df = pd.DataFrame(
            {"2024-01-31": {"Revenue": 100, "Net Income": 20}},
            index=["Revenue", "Net Income"],
        )
        result = _statement("NVDA", df, "income_stmt_annual", "annual")
        assert result["periods"] == ["2024-01-31"]
        assert result["data"]["2024-01-31"]["Revenue"] == 100
        assert result["data"]["2024-01-31"]["Net Income"] == 20

    def test_frame_drops_na_columns(self):
        df = pd.DataFrame(
            {"2024-01-31": {"Revenue": 100}, "2023-01-31": {"Revenue": np.nan}},
            index=["Revenue"],
        )
        result = _statement("NVDA", df, "test", "annual")
        assert "2023-01-31" not in result["periods"]

    def test_includes_currency(self):
        df = pd.DataFrame({"2024-01-31": {"Revenue": 100}}, index=["Revenue"])
        result = _statement("NVDA", df, "test", "annual", currency="USD")
        assert result["currency"] == "USD"


class TestValidateTicker:
    def test_valid_tickers(self):
        assert _validate_ticker("NVDA") is None
        assert _validate_ticker("AAPL") is None
        assert _validate_ticker("BRK.B") is None
        assert _validate_ticker("MSFT") is None
        assert _validate_ticker("ABC-123") is None

    def test_invalid_tickers(self):
        err = _validate_ticker("")
        assert err is not None
        assert err["error"] is not None
        assert err["retryable"] is False

        err = _validate_ticker("INVALID!!")
        assert err is not None

        err = _validate_ticker("A" * 16)
        assert err is not None

    def test_edge_cases(self):
        err = _validate_ticker("NVDA!")
        assert err is not None


class TestCached:
    def test_cache_hit(self):
        call_count = 0

        def loader():
            nonlocal call_count
            call_count += 1
            return {"value": call_count}

        key = ("test", "key")
        result1 = _cached(key, loader)
        result2 = _cached(key, loader)

        assert call_count == 1
        # Second call returns cached result with "cached": True
        assert result1 == {"value": 1}
        assert result2 == {"cached": True, "value": 1}

    def test_cache_miss_on_error(self):
        call_count = 0

        def loader():
            nonlocal call_count
            call_count += 1
            return {"error": "fail"}

        key = ("test", "key2")
        result1 = _cached(key, loader)
        result2 = _cached(key, loader)

        # Should call loader every time since error not cached
        assert call_count == 2


class TestState:
    def test_create_initial_state(self):
        state = create_initial_state(
            company="NVIDIA",
            messages=[{"role": "user", "content": "hello"}],
            question="What is revenue?",
            ticker="NVDA",
        )
        assert state["company"] == "NVIDIA"
        assert state["ticker"] == "NVDA"
        assert len(state["messages"]) == 2
        assert state["messages"][0]["role"] == "user"
        assert state["messages"][0]["content"] == "hello"
        assert state["messages"][1]["role"] == "user"
        assert state["messages"][1]["content"] == "What is revenue?"

    def test_create_initial_state_no_ticker(self):
        state = create_initial_state(
            company="NVIDIA",
            messages=[],
            question="What is revenue?",
        )
        assert state["ticker"] == ""

    def test_agent_state_fields(self):
        # Verify AgentState has only expected fields
        state: AgentState = {
            "company": "NVDA",
            "ticker": "NVDA",
            "messages": [],
        }
        assert "company" in state
        assert "ticker" in state
        assert "messages" in state


class TestUserInput:
    @patch("user_input.yf.Search")
    def test_search_tickers(self, mock_search):
        mock_quotes = [
            {"symbol": "NVDA", "shortname": "NVIDIA Corp", "exchDisp": "NASDAQ", "quoteType": "EQUITY"},
            {"symbol": "NVDA1", "shortname": "NVIDIA Corp 1", "exchDisp": "NASDAQ", "quoteType": "EQUITY"},
            {"symbol": "BOND", "shortname": "Bond Fund", "exchDisp": "NASDAQ", "quoteType": "ETF"},
        ]
        mock_search.return_value.quotes = mock_quotes

        results = search_tickers("NVIDIA")

        assert len(results) == 2
        assert results[0]["symbol"] == "NVDA"
        assert results[0]["name"] == "NVIDIA Corp"
        assert results[0]["exchange"] == "NASDAQ"

    @patch("user_input.yf.Search")
    def test_search_tickers_empty(self, mock_search):
        mock_search.return_value.quotes = []
        results = search_tickers("INVALID")
        assert results == ()

    @patch("user_input.yf.Search")
    def test_search_tickers_exception(self, mock_search):
        mock_search.side_effect = Exception("Network error")
        # Clear cache before test
        import user_input
        user_input._search_cache.clear()
        results = search_tickers("NVIDIA")
        assert results == ()

    def test_search_tickers_no_cache_on_failure(self):
        """Verify failures are not cached - subsequent call should retry and succeed."""
        import user_input
        user_input._search_cache.clear()
        with patch("user_input.yf.Search") as mock_search:
            mock_search.side_effect = Exception("Network error")
            r1 = search_tickers("FAIL")
            assert r1 == ()
            # Second call should also attempt (not cached) and succeed
            mock_search.side_effect = None
            mock_search.return_value.quotes = [
                {"symbol": "NVDA", "shortname": "NVIDIA Corp", "exchDisp": "NASDAQ", "quoteType": "EQUITY"},
            ]
            r2 = search_tickers("FAIL")
            assert r2 != ()
            assert r2[0]["symbol"] == "NVDA"


class TestFinancialTools:
    @patch("mcp_server.financial_tools.yf.Ticker")
    def test_get_financials_returns_dict(self, mock_ticker_class):
        """Test that get_financials returns a dict, not a coroutine."""
        ft._cache.clear()

        fake = MagicMock()
        fake.income_stmt = pd.DataFrame(
            {pd.Timestamp("2025-01-31"): {"Total Revenue": 100.0}},
            index=["Total Revenue"],
        )
        fake.get_info.return_value = {"financialCurrency": "USD"}
        mock_ticker_class.return_value = fake

        result = asyncio.run(ft.get_financials("NVDA", "annual"))

        assert isinstance(result, dict), f"Expected dict, got {type(result)}"
        assert "data" in result
        assert "2025-01-31" in result["data"]
        assert result["data"]["2025-01-31"]["Total Revenue"] == 100.0
        assert result["currency"] == "USD"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])