"""Entry points that run the monitor: used by the CLI (scheduled) and the API (manual)."""
import asyncio
import logging

from monitor import db
from monitor.agents import get_monitor_llm
from monitor.graph import MonitorDeps, build_monitor_graph
from monitor.notify import get_notifier

logger = logging.getLogger(__name__)


async def default_deps() -> MonitorDeps:
    from graph import create_graph  # the existing analyst agent + MCP tool server
    return MonitorDeps(
        analyst_graph=await create_graph(),
        llm=get_monitor_llm(),
        notifier=get_notifier(),
    )


async def execute_run(run_id: int, deps: MonitorDeps | None = None) -> dict | None:
    """Run the monitor graph for an already-created run row. Never raises."""
    notifier = None
    try:
        deps = deps or await default_deps()
        notifier = deps.notifier
        final = await build_monitor_graph(deps).ainvoke(
            {"run_id": run_id}, config={"recursion_limit": 200})
        return final.get("summary")
    except Exception as exc:
        logger.exception("monitor run %s failed", run_id)
        await asyncio.to_thread(db.finish_run, run_id, "failed", None, f"{type(exc).__name__}: {exc}"[:500])
        try:
            notifier = notifier or get_notifier()
            await notifier.send(f"Monitor run #{run_id} failed ({type(exc).__name__}). Check the logs.")
        except Exception:
            logger.exception("could not send the failure notice")
        return None


async def run_monitor(trigger: str = "schedule", deps: MonitorDeps | None = None) -> dict:
    """Start a run unless one is already in progress. Returns {run_id, ok} or {skipped}."""
    run_id = await asyncio.to_thread(db.try_start_run, trigger)
    if run_id is None:
        return {"skipped": "another run is already in progress"}
    summary = await execute_run(run_id, deps)
    ok = summary is not None and not summary.get("failed")
    return {"run_id": run_id, "ok": ok, "summary": summary}
