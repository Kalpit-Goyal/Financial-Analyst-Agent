"""The autonomous monitor as a LangGraph workflow.

load -> scan -> triage -> [ next -> investigate -> compose -> critic -> act ]* -> finish

  scan         deterministic: price signals, triggers, cooldown (no LLM)
  triage       LLM decides which candidates deserve a deep dive
  investigate  the existing analyst agent, with tools, writes a draft
  compose      LLM turns the draft into a structured brief
  critic       LLM fact-checks the brief against raw tool data; may send it back
  act          sends the alert (or a signals-only alert if verification failed) and logs it
"""
import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any, Callable, TypedDict

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.graph import END, START, StateGraph

from monitor import agents, db, signals as sig
from monitor import config as cfg
from monitor import notify
from state import create_initial_state

logger = logging.getLogger(__name__)


class MonitorState(TypedDict, total=False):
    run_id: int
    user_id: int | None           # None = scheduled run over every account
    watchlist: list[dict]         # grouped by ticker: {ticker, name, watchers, notes}
    candidates: list[dict]
    queue: list[str]
    current: dict
    results: list[dict]
    skipped: list[dict]
    errors: list[str]
    quiet: int
    summary: dict


@dataclass
class MonitorDeps:
    analyst_graph: Any                      # compiled chat graph (analyst + MCP tools)
    llm: Any                                # LLM for triage / compose / critic
    notifier: Any                           # object with: async send(text) -> bool
    signal_fn: Callable[[str], dict] = sig.compute_signals
    now_fn: Callable = db.utcnow


# ------------------------------------------------------------------ helpers

def content_text(content) -> str:
    """Flatten LangChain message content (str or list of blocks) to text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            b.get("text", "") if isinstance(b, dict) else str(b) for b in content
        )
    return str(content)


def build_task(current: dict) -> str:
    triggers = "; ".join(t["detail"] for t in current["triggers"])
    task = (
        f"Automated monitoring alert for {current['name'] or current['ticker']} ({current['ticker']}).\n"
        f"Triggers: {triggers}.\n"
        f"Market signals computed from price data: {json.dumps(current['signals'])}\n"
    )
    notes = list(dict.fromkeys(current.get("notes") or []))
    if notes:
        task += f"The user's note on this stock (context only): {'; '.join(notes)}\n"
    task += (
        "\nInvestigate what the financial data says about this situation. Fetch what you need "
        "with the tools (statements, valuation, cash flow as relevant). Use the calculate tool "
        "for every ratio, margin or growth figure you state.\n"
        "Write: (1) what is happening, (2) whether fundamentals support or contradict it, "
        "(3) the main risks. State currency and period for each figure. "
        "Do not speculate beyond the data and say plainly what you could not verify."
    )
    if current.get("feedback"):
        task += (
            "\n\nYOUR PREVIOUS DRAFT:\n" + current["draft"][:4000] +
            "\n\nA fact-checker rejected it for these reasons. Fix every one, using tools "
            "if you need more data, and remove claims you cannot support:\n- "
            + "\n- ".join(current["feedback"])
        )
    return task


def evidence_text(current: dict) -> str:
    return f"[market signals] {json.dumps(current['signals'])}\n" + "\n\n".join(current["evidence"])


def _fail(current: dict, why: str) -> dict:
    return {**current, "failed": why}


# -------------------------------------------------------------------- graph

def build_monitor_graph(deps: MonitorDeps):

    async def load(state: MonitorState):
        # One account (manual run) or every account (scheduled run).
        items = await asyncio.to_thread(db.list_watchlist, state.get("user_id"))
        grouped: dict[str, dict] = {}
        for item in items:
            entry = grouped.setdefault(item["ticker"], {
                "ticker": item["ticker"], "name": item.get("name"),
                "watchers": [], "notes": [],
            })
            if item.get("name") and not entry["name"]:
                entry["name"] = item["name"]
            if item.get("user_id") is not None:
                entry["watchers"].append(item["user_id"])
            if item.get("note"):
                entry["notes"].append(item["note"])
        return {"watchlist": list(grouped.values()), "results": [], "skipped": [], "errors": [],
                "quiet": 0, "candidates": [], "queue": []}

    async def scan(state: MonitorState):
        sem = asyncio.Semaphore(3)

        async def one(item):
            async with sem:
                try:
                    return item, await asyncio.to_thread(deps.signal_fn, item["ticker"])
                except Exception as exc:
                    return item, {"ticker": item["ticker"], "ok": False, "error": type(exc).__name__}

        scanned = await asyncio.gather(*(one(i) for i in state["watchlist"]))
        candidates, skipped, errors, quiet = [], [], [], 0
        now = deps.now_fn()

        for item, signals in scanned:
            ticker = item["ticker"]
            if not signals.get("ok"):
                errors.append(f"{ticker}: {signals.get('error', 'no data')}")
                continue
            triggers = sig.evaluate_triggers(signals)
            if not sig.qualifies(triggers):
                quiet += 1
                continue
            # A ticker watched by several accounts is investigated once; the
            # cooldown is applied per account so each one gets its own alerts.
            watchers = item["watchers"] or [None]
            cooled = []
            for watcher in watchers:
                last = await asyncio.to_thread(db.last_alert_time, ticker, watcher)
                if last is None or (now - last).total_seconds() >= cfg.COOLDOWN_HOURS * 3600:
                    cooled.append(watcher)
            if not cooled:
                skipped.append({"ticker": ticker, "reason": f"alerted within the last {cfg.COOLDOWN_HOURS}h"})
                continue
            candidates.append({
                "ticker": ticker, "name": item.get("name"), "notes": item["notes"],
                "watchers": cooled,
                "signals": signals, "triggers": triggers, "score": sig.score(triggers),
                "signal_line": sig.describe(signals, triggers),
            })
        return {"candidates": candidates, "skipped": skipped, "errors": errors, "quiet": quiet}

    async def triage(state: MonitorState):
        if not state["candidates"]:
            return {"queue": []}
        decisions = await agents.triage(deps.llm, state["candidates"])
        by_score = sorted(state["candidates"], key=lambda c: c["score"], reverse=True)
        queue = [c["ticker"] for c in by_score if decisions[c["ticker"]]["escalate"]]
        skipped = list(state["skipped"]) + [
            {"ticker": c["ticker"], "reason": f"triage: {decisions[c['ticker']]['reason']}"}
            for c in by_score if not decisions[c["ticker"]]["escalate"]
        ]
        return {"queue": queue, "skipped": skipped}

    async def next_ticker(state: MonitorState):
        queue = list(state["queue"])
        ticker = queue.pop(0)
        cand = next(c for c in state["candidates"] if c["ticker"] == ticker)
        current = {
            "ticker": ticker, "name": cand["name"], "notes": cand.get("notes", []),
            "watchers": cand.get("watchers", []),
            "signals": cand["signals"], "triggers": cand["triggers"],
            "signal_line": cand["signal_line"], "attempt": 0, "feedback": [],
            "draft": "", "evidence": [], "brief": None, "verdict": None, "failed": None,
        }
        return {"queue": queue, "current": current}

    async def investigate(state: MonitorState):
        cur = state["current"]
        initial = create_initial_state(
            company=cur["name"] or cur["ticker"], messages=[],
            question=build_task(cur), ticker=cur["ticker"],
        )
        try:
            result = await agents.call_with_retry(
                lambda: deps.analyst_graph.ainvoke(
                    initial, config={"recursion_limit": 50, "tags": ["monitor"]})
            )
        except Exception as exc:
            logger.exception("investigation failed for %s", cur["ticker"])
            return {"current": _fail(cur, f"investigation failed ({type(exc).__name__})")}

        messages = result["messages"]
        draft = ""
        for m in reversed(messages):
            if isinstance(m, AIMessage) and not m.tool_calls:
                draft = content_text(m.content)
                break
        # Only the tool outputs from this turn count as evidence.
        evidence = list(cur["evidence"])
        for m in reversed(messages):
            if isinstance(m, HumanMessage):
                break
            if isinstance(m, ToolMessage):
                evidence.append(content_text(m.content))
        if not draft.strip():
            return {"current": _fail(cur, "analyst returned no text")}
        return {"current": {**cur, "draft": draft, "evidence": evidence}}

    async def compose(state: MonitorState):
        cur = state["current"]
        try:
            brief = await agents.compose(
                deps.llm, ticker=cur["ticker"], signal_line=cur["signal_line"],
                draft=cur["draft"], evidence=evidence_text(cur))
        except Exception as exc:
            logger.exception("compose failed for %s", cur["ticker"])
            return {"current": _fail(cur, f"could not structure the analysis ({type(exc).__name__})")}
        return {"current": {**cur, "brief": brief}}

    async def critic(state: MonitorState):
        cur = state["current"]
        verdict = await agents.critique(
            deps.llm, brief=cur["brief"], signal_line=cur["signal_line"],
            evidence=evidence_text(cur))
        if verdict["approved"]:
            return {"current": {**cur, "verdict": verdict}}
        return {"current": {**cur, "verdict": verdict, "attempt": cur["attempt"] + 1,
                            "feedback": verdict["issues"] or ["unsupported claims"]}}

    async def act(state: MonitorState):
        cur = state["current"]
        ticker, name = cur["ticker"], cur["name"]
        verified = bool(cur.get("brief") and cur.get("verdict") and cur["verdict"]["approved"])

        if verified:
            brief = cur["brief"]
            text = notify.format_verified_alert(
                ticker=ticker, name=name, brief=brief, signal_line=cur["signal_line"])
            headline, summary = brief["headline"], brief["summary"]
            stance, confidence = brief["stance"], brief["confidence"]
        else:
            if cur.get("failed"):
                reason = cur["failed"]
            else:
                # The critic's issues often quote the rejected claims, so they are logged
                # in the run summary but never put in the alert text.
                reason = "it did not pass the fact-check"
            text = notify.format_unverified_alert(
                ticker=ticker, name=name, signal_line=cur["signal_line"], reason=reason)
            # Nothing the model wrote is stored or scored when it was not verified.
            headline, summary = f"{ticker}: {cur['signal_line']}", reason
            stance, confidence = "neutral", "low"

        sent = await deps.notifier.send(text)
        # One row per account watching this ticker, so each history shows the alert.
        for watcher in cur.get("watchers") or [None]:
            await asyncio.to_thread(
                db.insert_alert, run_id=state["run_id"], user_id=watcher, ticker=ticker,
                triggers=[t["detail"] for t in cur["triggers"]], headline=headline, summary=summary,
                stance=stance, confidence=confidence, verified=verified,
                price_at_alert=cur["signals"].get("price"), sent=sent)
        results = list(state["results"]) + [{
            "ticker": ticker, "verified": verified, "sent": sent, "headline": headline,
            "revisions": cur["attempt"],
            "issues": [] if verified else (cur.get("verdict") or {}).get("issues", []),
        }]
        return {"results": results}

    async def finish(state: MonitorState):
        summary = {
            "watchlist": len(state.get("watchlist", [])),
            "quiet": state.get("quiet", 0),
            "candidates": len(state.get("candidates", [])),
            "alerts": state.get("results", []),
            "skipped": state.get("skipped", []),
            "errors": state.get("errors", []),
        }
        watchlist, errors = state.get("watchlist", []), state.get("errors", [])
        if watchlist and len(errors) == len(watchlist):
            # Nothing could be scanned (e.g. the data source is blocking this host).
            # Silence here would look like "no news", so fail the run and tell the owner.
            summary["failed"] = True
            await asyncio.to_thread(
                db.finish_run, state["run_id"], "failed", summary,
                "Price data could not be fetched for any watchlist ticker")
            await deps.notifier.send(
                f"Monitor run #{state['run_id']} could not fetch price data for any ticker. "
                "The data source may be rate limiting this host. Nothing was checked.")
        else:
            await asyncio.to_thread(db.finish_run, state["run_id"], "success", summary)
        return {"summary": summary}

    # --------------------------------------------------------- routing
    def after_load(state):
        return "scan" if state["watchlist"] else "finish"

    def after_triage(state):
        return "next_ticker" if state["queue"] else "finish"

    def after_investigate(state):
        return "act" if state["current"].get("failed") else "compose"

    def after_compose(state):
        return "act" if state["current"].get("failed") else "critic"

    def after_critic(state):
        cur = state["current"]
        if cur["verdict"]["approved"]:
            return "act"
        return "investigate" if cur["attempt"] <= cfg.MAX_REVISIONS else "act"

    def after_act(state):
        return "next_ticker" if state["queue"] else "finish"

    g = StateGraph(MonitorState)
    for name, fn in [("load", load), ("scan", scan), ("triage", triage), ("next_ticker", next_ticker),
                     ("investigate", investigate), ("compose", compose), ("critic", critic),
                     ("act", act), ("finish", finish)]:
        g.add_node(name, fn)

    g.add_edge(START, "load")
    g.add_conditional_edges("load", after_load, {"scan": "scan", "finish": "finish"})
    g.add_edge("scan", "triage")
    g.add_conditional_edges("triage", after_triage, {"next_ticker": "next_ticker", "finish": "finish"})
    g.add_edge("next_ticker", "investigate")
    g.add_conditional_edges("investigate", after_investigate, {"act": "act", "compose": "compose"})
    g.add_conditional_edges("compose", after_compose, {"act": "act", "critic": "critic"})
    g.add_conditional_edges("critic", after_critic, {"act": "act", "investigate": "investigate"})
    g.add_conditional_edges("act", after_act, {"next_ticker": "next_ticker", "finish": "finish"})
    g.add_edge("finish", END)
    return g.compile()
