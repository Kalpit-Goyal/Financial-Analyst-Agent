from datetime import timedelta

import pytest

from monitor import config as cfg
from monitor import db


def test_watchlist_add_list_remove(database):
    item = database.add_watchlist("nvda", "NVIDIA", "AI leader")
    assert item["ticker"] == "NVDA" and item["note"] == "AI leader"
    assert [i["ticker"] for i in database.list_watchlist()] == ["NVDA"]
    assert database.remove_watchlist("NVDA") is True
    assert database.remove_watchlist("NVDA") is False
    assert database.list_watchlist() == []


def test_adding_twice_updates_instead_of_duplicating(database):
    database.add_watchlist("AAPL", "Apple", None)
    database.add_watchlist("aapl", None, "services growth")
    items = database.list_watchlist()
    assert len(items) == 1
    assert items[0]["name"] == "Apple" and items[0]["note"] == "services growth"


def test_watchlist_limit(database, monkeypatch):
    monkeypatch.setattr(cfg, "MAX_WATCHLIST", 2)
    database.add_watchlist("A")
    database.add_watchlist("B")
    with pytest.raises(ValueError):
        database.add_watchlist("C")
    database.add_watchlist("A", note="re-adding an existing one is fine")


def test_only_one_run_at_a_time(database):
    first = database.try_start_run("manual")
    assert first is not None
    assert database.try_start_run("schedule") is None
    database.finish_run(first, "success", {"ok": True})
    assert database.try_start_run("schedule") is not None


def test_stale_running_run_is_replaced(database, monkeypatch):
    first = database.try_start_run("schedule")
    monkeypatch.setattr(cfg, "RUN_STALE_MINUTES", 0)
    second = database.try_start_run("schedule")
    assert second is not None and second != first
    runs = {r["id"]: r for r in database.list_runs()}
    assert runs[first]["status"] == "failed"


def test_run_summary_round_trip(database):
    rid = database.try_start_run("manual")
    database.finish_run(rid, "success", {"alerts": []})
    run = database.list_runs()[0]
    assert run["status"] == "success" and run["summary"] == {"alerts": []}


def _alert(database, ticker="NVDA", stance="bullish", price=100.0, verified=True):
    return database.insert_alert(
        run_id=1, ticker=ticker, triggers=["1-day move +6%"], headline="h", summary="s",
        stance=stance, confidence="medium", verified=verified, price_at_alert=price, sent=True)


def test_last_alert_time_and_listing(database):
    assert database.last_alert_time("NVDA") is None
    _alert(database)
    assert database.last_alert_time("nvda") is not None
    assert database.list_alerts()[0]["triggers"] == ["1-day move +6%"]


def test_stats_hit_rate_and_signed_return(database):
    a = _alert(database, stance="bullish")      # +10% -> hit
    b = _alert(database, stance="bearish")      # +5%  -> miss
    c = _alert(database, stance="neutral")      # not scored
    database.set_outcome(a, 110, 10.0, True)
    database.set_outcome(b, 105, 5.0, False)
    database.set_outcome(c, 101, 1.0, None)
    s = database.stats()
    assert s["alerts"] == 3 and s["scored"] == 2 and s["hits"] == 1
    assert s["hit_rate"] == 0.5
    assert s["avg_signed_return_pct"] == 2.5   # (+10 and -5) / 2


def test_stats_empty(database):
    s = database.stats()
    assert s["hit_rate"] is None and s["avg_signed_return_pct"] is None


def test_postgres_url_is_normalised():
    assert db._normalize_url("postgres://u:p@h/db").startswith("postgresql+psycopg://")
    assert db._normalize_url("postgresql://u:p@h/db").startswith("postgresql+psycopg://")
    assert db._normalize_url("sqlite:///x.db") == "sqlite:///x.db"
