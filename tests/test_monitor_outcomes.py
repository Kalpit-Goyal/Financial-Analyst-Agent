from datetime import timedelta

from monitor import config as cfg
from monitor import db
from monitor.outcomes import evaluate_outcomes


def add(database, stance, price=100.0):
    return database.insert_alert(
        run_id=1, ticker="NVDA", triggers=[], headline="h", summary="s", stance=stance,
        confidence="medium", verified=True, price_at_alert=price, sent=True)


def later():
    return db.utcnow() + timedelta(days=cfg.OUTCOME_HORIZON_DAYS + 1)


def test_recent_alerts_are_not_scored_yet(database):
    add(database, "bullish")
    assert evaluate_outcomes(price_fn=lambda t: 120.0) == 0
    assert database.list_alerts()[0]["outcome_at"] is None


def test_bullish_hit_and_bearish_miss(database):
    add(database, "bullish")
    add(database, "bearish")
    assert evaluate_outcomes(price_fn=lambda t: 110.0, now=later()) == 2
    by_stance = {a["stance"]: a for a in database.list_alerts()}
    assert by_stance["bullish"]["hit"] is True and by_stance["bullish"]["return_pct"] == 10.0
    assert by_stance["bearish"]["hit"] is False


def test_neutral_is_recorded_but_not_scored(database):
    add(database, "neutral")
    evaluate_outcomes(price_fn=lambda t: 90.0, now=later())
    alert = database.list_alerts()[0]
    assert alert["return_pct"] == -10.0 and alert["hit"] is None


def test_scored_alerts_are_not_rescored(database):
    add(database, "bullish")
    assert evaluate_outcomes(price_fn=lambda t: 110.0, now=later()) == 1
    assert evaluate_outcomes(price_fn=lambda t: 50.0, now=later()) == 0
    assert database.list_alerts()[0]["return_pct"] == 10.0


def test_price_lookup_failures_leave_the_alert_pending(database):
    add(database, "bullish")
    def boom(t):
        raise RuntimeError("yahoo down")
    assert evaluate_outcomes(price_fn=boom, now=later()) == 0
    assert evaluate_outcomes(price_fn=lambda t: None, now=later()) == 0
    assert database.list_alerts()[0]["outcome_at"] is None
