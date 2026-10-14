from datetime import date, datetime
from unittest.mock import MagicMock, patch

import pandas as pd

from monitor import signals as sig
from tests.monitor_fakes import make_signals


def types(signals):
    return {t["type"] for t in sig.evaluate_triggers(signals)}


def test_big_one_day_move_triggers():
    assert "move_1d" in types(make_signals("X", d1=-5.0))
    assert "move_1d" not in types(make_signals("X", d1=3.9))


def test_five_day_move_triggers():
    assert "move_5d" in types(make_signals("X", d1=0.1, d5=9.0))


def test_earnings_window():
    assert "earnings_soon" in types(make_signals("X", d1=0, d5=0, days_to_earnings=0))
    assert "earnings_soon" in types(make_signals("X", d1=0, d5=0, days_to_earnings=3))
    assert "earnings_soon" not in types(make_signals("X", d1=0, d5=0, days_to_earnings=4))


def test_52_week_context_alone_does_not_qualify():
    s = make_signals("X", d1=0.1, d5=0.1)
    s["pct_from_52w_high"] = -0.5
    triggers = sig.evaluate_triggers(s)
    assert any(t["type"] == "near_52w_high" for t in triggers)
    assert not sig.qualifies(triggers)


def test_failed_fetch_has_no_triggers():
    assert sig.evaluate_triggers(make_signals("X", ok=False)) == []


def test_score_grows_with_more_signals():
    one = sig.evaluate_triggers(make_signals("X", d1=5.0, d5=0.0))
    two = sig.evaluate_triggers(make_signals("X", d1=5.0, d5=9.0))
    assert sig.score(two) > sig.score(one)


def test_describe_has_price_and_triggers_only():
    s = make_signals("X", d1=5.0)
    line = sig.describe(s, sig.evaluate_triggers(s))
    assert "price 100 USD" in line and "1-day move +5.0%" in line


def _fake_ticker(closes, calendar=None):
    idx = pd.date_range("2026-01-01", periods=len(closes), freq="B")
    t = MagicMock()
    t.history.return_value = pd.DataFrame({"Close": closes}, index=idx)
    t.history_metadata = {"currency": "USD"}
    t.calendar = calendar if calendar is not None else {}
    return t


def test_compute_signals_from_price_history():
    closes = [100.0] * 20 + [100, 100, 100, 100, 100, 110]   # +10% on the last day
    t = _fake_ticker(closes, {"Earnings Date": [datetime(2026, 10, 15), date(2026, 1, 1)]})
    with patch.object(sig.yf, "Ticker", return_value=t):
        s = sig.compute_signals("NVDA", today=date(2026, 10, 14))
    assert s["ok"] and s["price"] == 110.0 and s["currency"] == "USD"
    assert s["change_1d_pct"] == 10.0 and s["change_5d_pct"] == 10.0
    assert s["days_to_earnings"] == 1 and s["next_earnings"] == "2026-10-15"
    assert s["pct_from_52w_high"] == 0.0


def test_compute_signals_handles_no_data_and_short_history():
    empty = MagicMock()
    empty.history.return_value = pd.DataFrame()
    with patch.object(sig.yf, "Ticker", return_value=empty):
        assert sig.compute_signals("ZZZ")["ok"] is False
    with patch.object(sig.yf, "Ticker", return_value=_fake_ticker([1.0, 2.0, 3.0])):
        assert sig.compute_signals("ZZZ")["ok"] is False


def test_missing_calendar_is_not_fatal():
    t = _fake_ticker([100.0] * 10)
    type(t).calendar = property(lambda self: (_ for _ in ()).throw(RuntimeError("yahoo down")))
    with patch.object(sig.yf, "Ticker", return_value=t):
        s = sig.compute_signals("NVDA")
    assert s["ok"] and s["next_earnings"] is None
