"""Command line entry point, used by the scheduled GitHub Action.

    python -m monitor.cli run        # scan the watchlist and send alerts
    python -m monitor.cli evaluate   # score old alerts against actual price moves
    python -m monitor.cli all        # evaluate, then run (what the schedule uses)
"""
import argparse
import asyncio
import json
import logging
import sys

from dotenv import load_dotenv

load_dotenv()

from monitor import db  # noqa: E402
from monitor.outcomes import evaluate_outcomes_async  # noqa: E402
from monitor.runner import run_monitor  # noqa: E402


async def _main(command: str) -> int:
    await asyncio.to_thread(db.init_db)
    code = 0

    if command in ("evaluate", "all"):
        n = await evaluate_outcomes_async()
        print(f"Scored {n} past alert(s).")

    if command in ("run", "all"):
        from graph import close_graph
        try:
            result = await run_monitor("schedule")
        finally:
            await close_graph()
        print(json.dumps(result, indent=2, default=str))
        if "skipped" not in result and not result.get("ok"):
            code = 1
    return code


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(prog="monitor")
    parser.add_argument("command", choices=["run", "evaluate", "all"])
    sys.exit(asyncio.run(_main(parser.parse_args().command)))


if __name__ == "__main__":
    main()
