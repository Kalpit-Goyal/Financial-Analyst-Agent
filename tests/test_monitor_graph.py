import asyncio

from monitor import config as cfg
from monitor import db
from monitor.agents import Brief, Triage, TriageItem, Verdict
from monitor.graph import MonitorDeps, build_monitor_graph
from monitor.runner import execute_run, run_monitor

from tests.monitor_fakes import (
    FakeAnalystGraph, FakeLLM, FakeNotifier, brief, make_signals, triage_all,
)


def run_graph(database, *, signals, llm, analyst=None, notifier=None, watch=("NVDA",), notes=None):
    for t in watch:
        database.add_watchlist(t, f"{t} Inc", (notes or {}).get(t))
    analyst = analyst or FakeAnalystGraph()
    notifier = notifier or FakeNotifier()
    deps = MonitorDeps(
        analyst_graph=analyst, llm=llm, notifier=notifier,
        signal_fn=lambda t: signals[t] if not isinstance(signals[t], Exception) else (_ for _ in ()).throw(signals[t]),
    )
    run_id = database.try_start_run("manual")
    state = asyncio.run(build_monitor_graph(deps).ainvoke({"run_id": run_id}, config={"recursion_limit": 200}))
    return state, analyst, notifier, run_id


def approved():
    return Verdict(approved=True, issues=[])


def rejected(*issues):
    return Verdict(approved=False, issues=list(issues))


def test_verified_alert_end_to_end(database):
    llm = FakeLLM({Triage: [triage_all("NVDA")], Brief: [brief()], Verdict: [approved()]})
    state, analyst, notifier, run_id = run_graph(database, signals={"NVDA": make_signals("NVDA")}, llm=llm)

    assert len(analyst.prompts) == 1
    assert "1-day move +6.0%" in analyst.prompts[0]
    assert len(notifier.sent) == 1 and "Margins expanded" in notifier.sent[0]
    assert "checked against data" in notifier.sent[0]

    alert = database.list_alerts()[0]
    assert alert["verified"] is True and alert["stance"] == "bullish" and alert["sent"] is True
    assert alert["price_at_alert"] == 100.0

    run = database.list_runs()[0]
    assert run["status"] == "success" and run["summary"]["alerts"][0]["verified"] is True


def test_critic_rejection_sends_the_analyst_back_with_the_issues(database):
    llm = FakeLLM({
        Triage: [triage_all("NVDA")], Brief: [brief()],
        Verdict: [rejected("Revenue growth of 20% is not in the data"), approved()],
    })
    state, analyst, notifier, _ = run_graph(database, signals={"NVDA": make_signals("NVDA")}, llm=llm)

    assert len(analyst.prompts) == 2
    assert "Revenue growth of 20% is not in the data" in analyst.prompts[1]
    assert "YOUR PREVIOUS DRAFT" in analyst.prompts[1]
    assert llm.count(Verdict) == 2
    assert database.list_alerts()[0]["verified"] is True
    assert state["results"][0]["revisions"] == 1


def test_never_verified_alert_withholds_model_claims(database):
    llm = FakeLLM({
        Triage: [triage_all("NVDA")], Brief: [brief("SECRET HEADLINE")],
        Verdict: [rejected("SECRET HEADLINE is not supported by the data")],
    })
    state, analyst, notifier, _ = run_graph(database, signals={"NVDA": make_signals("NVDA")}, llm=llm)

    assert len(analyst.prompts) == cfg.MAX_REVISIONS + 1      # first try plus the allowed rewrites
    text = notifier.sent[0]
    assert "SECRET HEADLINE" not in text and "could not be verified" in text
    assert "1-day move +6.0%" in text                          # the deterministic signals are still sent

    alert = database.list_alerts()[0]
    assert alert["verified"] is False and alert["stance"] == "neutral"   # never scored
    assert "SECRET HEADLINE" not in (alert["headline"] + alert["summary"])
    # the critic's wording is kept for debugging, but only in the owner-only run log
    assert "SECRET HEADLINE" in database.list_runs()[0]["summary"]["alerts"][0]["issues"][0]


def test_cooldown_prevents_repeat_alerts(database):
    database.insert_alert(run_id=0, ticker="NVDA", triggers=[], headline="h", summary="s",
                          stance="neutral", confidence="low", verified=True,
                          price_at_alert=1.0, sent=True)
    llm = FakeLLM({Triage: [triage_all("NVDA")]})
    state, analyst, notifier, _ = run_graph(database, signals={"NVDA": make_signals("NVDA")}, llm=llm)

    assert analyst.prompts == [] and notifier.sent == []
    assert llm.calls == []
    assert "alerted within" in state["skipped"][0]["reason"]


def test_triage_can_decline(database):
    llm = FakeLLM({Triage: [triage_all("NVDA", escalate=False)]})
    state, analyst, notifier, _ = run_graph(database, signals={"NVDA": make_signals("NVDA")}, llm=llm)
    assert analyst.prompts == [] and notifier.sent == []
    assert state["skipped"][0]["reason"] == "triage: test"


def test_quiet_tickers_cost_nothing(database):
    llm = FakeLLM({Triage: [triage_all("NVDA")]})
    state, analyst, notifier, _ = run_graph(
        database, signals={"NVDA": make_signals("NVDA", d1=0.5, d5=1.0)}, llm=llm)
    assert state["quiet"] == 1 and llm.calls == [] and analyst.prompts == []


def test_earnings_alone_is_a_trigger(database):
    llm = FakeLLM({Triage: [triage_all("NVDA")], Brief: [brief()], Verdict: [approved()]})
    sig = make_signals("NVDA", d1=0.1, d5=0.2, days_to_earnings=1)
    state, analyst, notifier, _ = run_graph(database, signals={"NVDA": sig}, llm=llm)
    assert "earnings in 1d" in analyst.prompts[0]


def test_one_bad_ticker_does_not_stop_the_run(database):
    llm = FakeLLM({Triage: [triage_all("AAPL")], Brief: [brief()], Verdict: [approved()]})
    signals = {"NVDA": RuntimeError("boom"), "TSLA": make_signals("TSLA", ok=False), "AAPL": make_signals("AAPL")}
    state, analyst, notifier, _ = run_graph(database, signals=signals, llm=llm, watch=("NVDA", "TSLA", "AAPL"))
    assert [r["ticker"] for r in state["results"]] == ["AAPL"]
    assert len(state["errors"]) == 2


def test_failed_delivery_is_recorded_not_fatal(database):
    llm = FakeLLM({Triage: [triage_all("NVDA")], Brief: [brief()], Verdict: [approved()]})
    state, *_ = run_graph(database, signals={"NVDA": make_signals("NVDA")}, llm=llm,
                          notifier=FakeNotifier(ok=False))
    assert database.list_alerts()[0]["sent"] is False
    assert state["results"][0]["sent"] is False
    assert database.list_runs()[0]["status"] == "success"


def test_investigation_failure_still_sends_signals_only(database):
    llm = FakeLLM({Triage: [triage_all("NVDA")]})
    analyst = FakeAnalystGraph(fail=RuntimeError("tool server down"))
    state, _, notifier, _ = run_graph(database, signals={"NVDA": make_signals("NVDA")}, llm=llm, analyst=analyst)
    assert "investigation failed" in notifier.sent[0]
    assert database.list_alerts()[0]["verified"] is False


def test_triage_failure_falls_back_to_score_ranking(database):
    llm = FakeLLM({Triage: [RuntimeError("model down")], Brief: [brief()], Verdict: [approved()]})
    state, analyst, notifier, _ = run_graph(database, signals={"NVDA": make_signals("NVDA")}, llm=llm)
    assert len(analyst.prompts) == 1 and len(notifier.sent) == 1


def test_critic_failure_means_unverified(database):
    llm = FakeLLM({Triage: [triage_all("NVDA")], Brief: [brief("SECRET")], Verdict: [RuntimeError("down")]})
    state, _, notifier, _ = run_graph(database, signals={"NVDA": make_signals("NVDA")}, llm=llm)
    assert "SECRET" not in notifier.sent[0]
    assert database.list_alerts()[0]["verified"] is False


def test_investigation_limit_per_run(database, monkeypatch):
    monkeypatch.setattr(cfg, "MAX_INVESTIGATIONS", 2)
    tickers = ("A", "B", "C", "D")
    llm = FakeLLM({Triage: [triage_all(*tickers)], Brief: [brief()], Verdict: [approved()]})
    signals = {t: make_signals(t, d1=5.0 + i) for i, t in enumerate(tickers)}
    state, analyst, notifier, _ = run_graph(database, signals=signals, llm=llm, watch=tickers)
    assert len(analyst.prompts) == 2
    assert {r["ticker"] for r in state["results"]} == {"D", "C"}   # strongest signals first
    assert len([s for s in state["skipped"] if "limit" in s["reason"]]) == 2


def test_the_owners_note_is_context_not_instruction(database):
    llm = FakeLLM({Triage: [triage_all("NVDA")], Brief: [brief()], Verdict: [approved()]})
    state, analyst, *_ = run_graph(
        database, signals={"NVDA": make_signals("NVDA")}, llm=llm, notes={"NVDA": "long-term AI play"})
    assert "long-term AI play" in analyst.prompts[0] and "context only" in analyst.prompts[0]


def test_empty_watchlist_finishes_cleanly(database):
    llm = FakeLLM({Triage: [triage_all()]})
    deps = MonitorDeps(analyst_graph=FakeAnalystGraph(), llm=llm, notifier=FakeNotifier())
    run_id = database.try_start_run("manual")
    state = asyncio.run(build_monitor_graph(deps).ainvoke({"run_id": run_id}))
    assert state["summary"]["watchlist"] == 0 and llm.calls == []
    assert database.list_runs()[0]["status"] == "success"


def test_run_monitor_refuses_to_overlap(database):
    database.try_start_run("manual")
    result = asyncio.run(run_monitor("schedule"))
    assert "skipped" in result


def test_crash_marks_the_run_failed_and_notifies(database):
    class Boom:
        async def ainvoke(self, *a, **k):
            raise RuntimeError("graph exploded")

    notifier = FakeNotifier()
    deps = MonitorDeps(analyst_graph=FakeAnalystGraph(), llm=FakeLLM({}), notifier=notifier,
                       signal_fn=lambda t: make_signals(t))
    database.add_watchlist("NVDA")
    run_id = database.try_start_run("manual")

    import monitor.runner as runner
    original = runner.build_monitor_graph
    runner.build_monitor_graph = lambda d: Boom()
    try:
        assert asyncio.run(execute_run(run_id, deps)) is None
    finally:
        runner.build_monitor_graph = original

    run = database.list_runs()[0]
    assert run["status"] == "failed" and "graph exploded" in run["error"]
    assert "failed" in notifier.sent[0]


def test_total_data_outage_fails_the_run_and_tells_the_owner(database):
    llm = FakeLLM({Triage: [triage_all("A", "B")]})
    signals = {"A": make_signals("A", ok=False), "B": RuntimeError("blocked")}
    state, _, notifier, _ = run_graph(database, signals=signals, llm=llm, watch=("A", "B"))
    run = database.list_runs()[0]
    assert run["status"] == "failed" and "any watchlist ticker" in run["error"]
    assert len(notifier.sent) == 1 and "could not fetch price data" in notifier.sent[0]


def test_partial_outage_is_still_a_success(database):
    llm = FakeLLM({Triage: [triage_all("B")], Brief: [brief()], Verdict: [approved()]})
    signals = {"A": make_signals("A", ok=False), "B": make_signals("B")}
    run_graph(database, signals=signals, llm=llm, watch=("A", "B"))
    assert database.list_runs()[0]["status"] == "success"


def test_run_monitor_reports_failure_for_the_cli_exit_code(database):
    deps = MonitorDeps(analyst_graph=FakeAnalystGraph(), llm=FakeLLM({}), notifier=FakeNotifier(),
                       signal_fn=lambda t: make_signals(t, ok=False))
    database.add_watchlist("NVDA")
    result = asyncio.run(run_monitor("schedule", deps))
    assert result["ok"] is False
