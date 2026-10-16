import pytest

from monitor import config as cfg


def test_watchlist_add_list_remove(database, user):
    item = database.add_watchlist(user["id"], "nvda", "NVIDIA", "AI leader")
    assert item["ticker"] == "NVDA" and item["note"] == "AI leader"
    assert [i["ticker"] for i in database.list_watchlist(user["id"])] == ["NVDA"]
    assert database.remove_watchlist(user["id"], "NVDA") is True
    assert database.remove_watchlist(user["id"], "NVDA") is False
    assert database.list_watchlist(user["id"]) == []


def test_adding_twice_updates_instead_of_duplicating(database, user):
    database.add_watchlist(user["id"], "AAPL", "Apple", None)
    database.add_watchlist(user["id"], "aapl", None, "services growth")
    items = database.list_watchlist(user["id"])
    assert len(items) == 1
    assert items[0]["name"] == "Apple" and items[0]["note"] == "services growth"


def test_watchlists_are_isolated_per_account(database, user):
    other = database.create_user("other@example.com", "Other", "scrypt:00:00")
    database.add_watchlist(user["id"], "NVDA")
    database.add_watchlist(other["id"], "AAPL")
    assert [i["ticker"] for i in database.list_watchlist(user["id"])] == ["NVDA"]
    assert [i["ticker"] for i in database.list_watchlist(other["id"])] == ["AAPL"]
    # None = every account (what scheduled scans load)
    assert [i["ticker"] for i in database.list_watchlist(None)] == ["AAPL", "NVDA"]
    # Both accounts may watch the same ticker.
    database.add_watchlist(other["id"], "NVDA")
    assert len(database.list_watchlist(None)) == 3
    assert database.remove_watchlist(other["id"], "NVDA") is True
    assert [i["ticker"] for i in database.list_watchlist(user["id"])] == ["NVDA"]


def test_watchlist_limit_is_per_account(database, user, monkeypatch):
    other = database.create_user("other@example.com", "Other", "scrypt:00:00")
    monkeypatch.setattr(cfg, "MAX_WATCHLIST", 2)
    database.add_watchlist(user["id"], "A")
    database.add_watchlist(user["id"], "B")
    with pytest.raises(ValueError):
        database.add_watchlist(user["id"], "C")
    database.add_watchlist(user["id"], "A", note="re-adding an existing one is fine")
    database.add_watchlist(other["id"], "C")  # the other account has its own limit


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


def test_runs_and_alerts_are_scoped_per_account(database, user):
    other = database.create_user("other@example.com", "Other", "scrypt:00:00")
    mine = database.try_start_run("manual", user["id"])
    database.finish_run(mine, "success", {"alerts": []})
    database.try_start_run("schedule")  # system run, no account
    database.insert_alert(run_id=mine, ticker="NVDA", triggers=[], headline="h", summary="s",
                          stance="bullish", confidence="low", verified=True,
                          price_at_alert=1.0, sent=True, user_id=user["id"])
    assert [r["id"] for r in database.list_runs(user["id"])] == [mine]
    assert len(database.list_runs()) == 2
    assert len(database.list_alerts(user["id"])) == 1
    assert database.list_alerts(other["id"]) == []
    assert database.stats(user["id"])["alerts"] == 1
    assert database.stats(other["id"])["alerts"] == 0


def _alert(database, ticker="NVDA", stance="bullish", price=100.0, verified=True, user_id=None):
    return database.insert_alert(
        run_id=1, user_id=user_id, ticker=ticker, triggers=["1-day move +6%"], headline="h", summary="s",
        stance=stance, confidence="medium", verified=verified, price_at_alert=price, sent=True)


def test_last_alert_time_and_listing(database):
    assert database.last_alert_time("NVDA") is None
    _alert(database)
    assert database.last_alert_time("nvda") is not None
    assert database.list_alerts()[0]["triggers"] == ["1-day move +6%"]


def test_last_alert_time_per_account(database, user):
    other = database.create_user("other@example.com", "Other", "scrypt:00:00")
    _alert(database, user_id=user["id"])
    assert database.last_alert_time("NVDA", user["id"]) is not None
    assert database.last_alert_time("NVDA", other["id"]) is None
    assert database.last_alert_time("NVDA") is not None  # unfiltered still sees it


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
    from monitor import db
    assert db._normalize_url("postgres://u:p@h/db").startswith("postgresql+psycopg://")
    assert db._normalize_url("postgresql://u:p@h/db").startswith("postgresql+psycopg://")
    assert db._normalize_url("sqlite:///x.db") == "sqlite:///x.db"


def test_legacy_database_is_upgraded(tmp_path, monkeypatch):
    """A pre-accounts database (global watchlist, no user_id) is migrated on startup."""
    from sqlalchemy import inspect, text

    from monitor import db

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'legacy.db'}")
    db.reset_engine()
    with db.get_engine().begin() as conn:
        conn.execute(text(
            "CREATE TABLE watchlist (id INTEGER PRIMARY KEY, ticker VARCHAR(20) NOT NULL UNIQUE,"
            " name VARCHAR(120), note TEXT, active BOOLEAN NOT NULL DEFAULT 1, added_at DATETIME NOT NULL)"))
        conn.execute(text(
            "CREATE TABLE runs (id INTEGER PRIMARY KEY, trigger VARCHAR(20), status VARCHAR(20) NOT NULL,"
            " started_at DATETIME NOT NULL, finished_at DATETIME, summary TEXT, error TEXT)"))
        conn.execute(text(
            "CREATE TABLE alerts (id INTEGER PRIMARY KEY, run_id INTEGER, ticker VARCHAR(20) NOT NULL,"
            " created_at DATETIME NOT NULL, triggers TEXT, headline TEXT, summary TEXT, stance VARCHAR(10),"
            " confidence VARCHAR(10), verified BOOLEAN NOT NULL DEFAULT 0, price_at_alert FLOAT,"
            " sent BOOLEAN NOT NULL DEFAULT 0, outcome_at DATETIME, price_after FLOAT,"
            " return_pct FLOAT, hit BOOLEAN)"))

    db.init_db()

    inspector = inspect(db.get_engine())
    for table in ("watchlist", "runs", "alerts"):
        assert "user_id" in {c["name"] for c in inspector.get_columns(table)}
    assert {"users", "sessions", "conversations", "messages"} <= set(inspector.get_table_names())

    user = db.create_user("upgraded@example.com", None, "scrypt:00:00")
    db.add_watchlist(user["id"], "NVDA")
    assert [i["ticker"] for i in db.list_watchlist(user["id"])] == ["NVDA"]
    db.reset_engine()


# ------------------------------------------------------------------ accounts

def test_create_user_rejects_duplicate_email(database):
    database.create_user("A@Example.com ", "A", "scrypt:00:00")
    with pytest.raises(ValueError):
        database.create_user("a@example.com", "B", "scrypt:00:00")
    assert database.get_user_by_email("a@example.com")["name"] == "A"


def test_sessions_round_trip_and_expiry(database, user):
    database.create_session(user["id"], "hash-1", ttl_days=30)
    assert database.user_for_session("hash-1")["id"] == user["id"]
    assert database.user_for_session("hash-2") is None
    database.delete_session("hash-1")
    assert database.user_for_session("hash-1") is None


# -------------------------------------------------------------- chat history

def test_conversation_round_trip(database, user):
    other = database.create_user("other@example.com", "Other", "scrypt:00:00")
    cid = database.upsert_conversation(user["id"], "nvda", "NVIDIA")
    assert database.upsert_conversation(user["id"], "NVDA", "NVIDIA Corp") == cid  # one per ticker

    database.add_message(cid, "user", "What was the latest revenue?")
    database.add_message(cid, "assistant", "Revenue was 96.2B (USD, Q2).",
                         tools=["get_financials"])

    conversations = database.list_conversations(user["id"])
    assert len(conversations) == 1
    assert conversations[0]["ticker"] == "NVDA"
    assert conversations[0]["company"] == "NVIDIA Corp"   # updated by the upsert
    assert conversations[0]["message_count"] == 2
    assert "Revenue was 96.2B" in conversations[0]["preview"]
    assert database.list_conversations(other["id"]) == []

    messages = database.list_messages(cid)
    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert messages[1]["tools"] == ["get_financials"] and messages[1]["error"] is False

    assert database.conversation_owned(cid, user["id"]) is True
    assert database.conversation_owned(cid, other["id"]) is False
    assert database.delete_conversation(cid, other["id"]) is False
    assert database.delete_conversation(cid, user["id"]) is True
    assert database.list_messages(cid) == []
    assert database.list_conversations(user["id"]) == []
