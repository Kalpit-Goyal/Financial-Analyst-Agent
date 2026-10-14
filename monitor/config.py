"""Tunable settings for the autonomous monitor (all overridable via environment)."""
import os


def _float(name: str, default: str) -> float:
    return float(os.getenv(name, default))


def _int(name: str, default: str) -> int:
    return int(os.getenv(name, default))


# Deterministic triggers: what makes a ticker a candidate for investigation.
MOVE_1D_PCT = _float("MONITOR_MOVE_1D_PCT", "4")        # |1-day move| at or above this
MOVE_5D_PCT = _float("MONITOR_MOVE_5D_PCT", "8")        # |5-day move| at or above this
EARNINGS_WINDOW_DAYS = _int("MONITOR_EARNINGS_DAYS", "3")
NEAR_52W_PCT = _float("MONITOR_NEAR_52W_PCT", "2")      # context signal only

# Agent behaviour.
COOLDOWN_HOURS = _int("MONITOR_COOLDOWN_HOURS", "24")   # no repeat alert for a ticker inside this window
MAX_INVESTIGATIONS = _int("MONITOR_MAX_INVESTIGATIONS", "3")
MAX_REVISIONS = _int("MONITOR_MAX_REVISIONS", "2")      # critic-triggered rewrites per ticker
EVIDENCE_CHARS = _int("MONITOR_EVIDENCE_CHARS", "12000")

# Track record.
OUTCOME_HORIZON_DAYS = _int("MONITOR_OUTCOME_DAYS", "7")

# Limits and resilience.
MAX_WATCHLIST = _int("MONITOR_MAX_WATCHLIST", "25")
LLM_RETRIES = _int("MONITOR_LLM_RETRIES", "3")
LLM_RETRY_SLEEP = _float("MONITOR_LLM_RETRY_SLEEP", "20")
RUN_STALE_MINUTES = _int("MONITOR_RUN_STALE_MIN", "45")
