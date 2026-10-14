"""Deterministic market signals. No LLM here: cheap, testable, and the trigger layer.

compute_signals() pulls price history (and the next earnings date when available);
evaluate_triggers() is a pure function that turns those numbers into named triggers.
"""
from datetime import date, datetime

import yfinance as yf

from monitor import config as cfg

# A ticker only becomes a candidate if at least one PRIMARY trigger fires.
# Context triggers add information but never qualify on their own.
PRIMARY = {"move_1d", "move_5d", "earnings_soon"}


def _pct(new: float, old: float) -> float | None:
    return round((new / old - 1) * 100, 2) if old else None


def _next_earnings(ticker_obj, today: date) -> date | None:
    try:
        calendar = ticker_obj.calendar
    except Exception:
        return None
    if not isinstance(calendar, dict):
        return None
    candidates = []
    for d in calendar.get("Earnings Date") or []:
        if isinstance(d, datetime):
            d = d.date()
        if isinstance(d, date) and d >= today:
            candidates.append(d)
    return min(candidates) if candidates else None


def compute_signals(ticker: str, today: date | None = None) -> dict:
    today = today or date.today()
    t = yf.Ticker(ticker)
    hist = t.history(period="1y")
    if hist is None or hist.empty or "Close" not in hist:
        return {"ticker": ticker, "ok": False, "error": "no price data returned"}

    closes = hist["Close"].dropna()
    if len(closes) < 6:
        return {"ticker": ticker, "ok": False, "error": "not enough price history"}

    last, prev, week_ago = float(closes.iloc[-1]), float(closes.iloc[-2]), float(closes.iloc[-6])
    high, low = float(closes.max()), float(closes.min())

    currency = None
    try:
        currency = (t.history_metadata or {}).get("currency")
    except Exception:
        pass

    earnings = _next_earnings(t, today)
    return {
        "ticker": ticker,
        "ok": True,
        "price": round(last, 4),
        "currency": currency,
        "as_of": closes.index[-1].date().isoformat() if hasattr(closes.index[-1], "date") else None,
        "change_1d_pct": _pct(last, prev),
        "change_5d_pct": _pct(last, week_ago),
        "pct_from_52w_high": _pct(last, high),
        "pct_from_52w_low": _pct(last, low),
        "next_earnings": earnings.isoformat() if earnings else None,
        "days_to_earnings": (earnings - today).days if earnings else None,
    }


def evaluate_triggers(signals: dict) -> list[dict]:
    """Return the triggers that fired, each {type, detail, weight}."""
    if not signals.get("ok"):
        return []

    fired = []
    d1, d5 = signals.get("change_1d_pct"), signals.get("change_5d_pct")
    if d1 is not None and abs(d1) >= cfg.MOVE_1D_PCT:
        fired.append({"type": "move_1d", "detail": f"1-day move {d1:+.1f}%",
                      "weight": abs(d1) / cfg.MOVE_1D_PCT})
    if d5 is not None and abs(d5) >= cfg.MOVE_5D_PCT:
        fired.append({"type": "move_5d", "detail": f"5-day move {d5:+.1f}%",
                      "weight": abs(d5) / cfg.MOVE_5D_PCT})

    days = signals.get("days_to_earnings")
    if days is not None and 0 <= days <= cfg.EARNINGS_WINDOW_DAYS:
        when = "today" if days == 0 else f"in {days}d"
        fired.append({"type": "earnings_soon", "detail": f"earnings {when}", "weight": 1.5})

    from_high, from_low = signals.get("pct_from_52w_high"), signals.get("pct_from_52w_low")
    if from_high is not None and from_high >= -cfg.NEAR_52W_PCT:
        fired.append({"type": "near_52w_high", "detail": "at/near 52-week high", "weight": 0.5})
    if from_low is not None and from_low <= cfg.NEAR_52W_PCT:
        fired.append({"type": "near_52w_low", "detail": "at/near 52-week low", "weight": 0.5})
    return fired


def qualifies(triggers: list[dict]) -> bool:
    return any(t["type"] in PRIMARY for t in triggers)


def score(triggers: list[dict]) -> float:
    return round(sum(t["weight"] for t in triggers), 2)


def describe(signals: dict, triggers: list[dict]) -> str:
    """One-line human summary of the signals, safe to show without any LLM claims."""
    parts = [t["detail"] for t in triggers]
    price = signals.get("price")
    if price is not None:
        parts.insert(0, f"price {price:g} {signals.get('currency') or ''}".strip())
    return "; ".join(parts) if parts else "no triggers"
