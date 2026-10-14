"""Self-evaluation: score past alerts against what the price actually did.

An alert is scored OUTCOME_HORIZON_DAYS after it was sent. Bullish counts as a hit
if the price rose, bearish if it fell. Neutral and unverified alerts are not scored.
"""
import asyncio
import logging
from datetime import timedelta

import yfinance as yf

from monitor import config as cfg
from monitor import db

logger = logging.getLogger(__name__)


def latest_price(ticker: str) -> float | None:
    hist = yf.Ticker(ticker).history(period="5d")
    if hist is None or hist.empty or "Close" not in hist:
        return None
    closes = hist["Close"].dropna()
    return float(closes.iloc[-1]) if len(closes) else None


def _score(stance: str, return_pct: float) -> bool | None:
    if stance == "bullish":
        return return_pct > 0
    if stance == "bearish":
        return return_pct < 0
    return None


def evaluate_outcomes(price_fn=latest_price, now=None) -> int:
    """Score every alert old enough and not yet scored. Returns how many were updated."""
    now = now or db.utcnow()
    cutoff = now - timedelta(days=cfg.OUTCOME_HORIZON_DAYS)
    updated = 0
    for alert in db.pending_outcome_alerts(cutoff):
        try:
            price = price_fn(alert["ticker"])
        except Exception:
            logger.warning("could not price %s for outcome scoring", alert["ticker"])
            continue
        if price is None or not alert["price_at_alert"]:
            continue
        ret = round((price / alert["price_at_alert"] - 1) * 100, 2)
        db.set_outcome(alert["id"], price, ret, _score(alert["stance"], ret))
        updated += 1
    return updated


async def evaluate_outcomes_async(price_fn=latest_price) -> int:
    return await asyncio.to_thread(evaluate_outcomes, price_fn)
