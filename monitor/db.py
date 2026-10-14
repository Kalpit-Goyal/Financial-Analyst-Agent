"""Persistence for the monitor: watchlist, run log, and alert history.

Uses SQLAlchemy Core so the same code runs on SQLite (local dev) and Postgres
(set DATABASE_URL, e.g. a free Neon database, so data survives redeploys).
All functions are synchronous; call them with asyncio.to_thread from async code.
"""
import json
import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import (
    Boolean, Column, DateTime, Float, Integer, MetaData, String, Table, Text,
    and_, create_engine, delete, func, insert, select, update,
)

from monitor import config as cfg

metadata = MetaData()

watchlist = Table(
    "watchlist", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("ticker", String(20), nullable=False, unique=True),
    Column("name", String(120)),
    Column("note", Text),
    Column("active", Boolean, nullable=False, default=True),
    Column("added_at", DateTime, nullable=False),
)

runs = Table(
    "runs", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("trigger", String(20)),
    Column("status", String(20), nullable=False),  # running | success | failed
    Column("started_at", DateTime, nullable=False),
    Column("finished_at", DateTime),
    Column("summary", Text),  # JSON
    Column("error", Text),
)

alerts = Table(
    "alerts", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("run_id", Integer),
    Column("ticker", String(20), nullable=False),
    Column("created_at", DateTime, nullable=False),
    Column("triggers", Text),  # JSON list
    Column("headline", Text),
    Column("summary", Text),
    Column("stance", String(10)),       # bullish | bearish | neutral
    Column("confidence", String(10)),
    Column("verified", Boolean, nullable=False, default=False),
    Column("price_at_alert", Float),
    Column("sent", Boolean, nullable=False, default=False),
    Column("outcome_at", DateTime),
    Column("price_after", Float),
    Column("return_pct", Float),
    Column("hit", Boolean),             # None = not scored (neutral or pending)
)

_engine = None


def utcnow() -> datetime:
    """Naive UTC timestamp (stored and compared consistently on SQLite and Postgres)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _iso(dt):
    return dt.isoformat() + "Z" if dt else None


def _normalize_url(url: str) -> str:
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


def get_engine():
    global _engine
    if _engine is None:
        url = _normalize_url(os.getenv("DATABASE_URL", "sqlite:///watchlist.db"))
        kwargs = {"pool_pre_ping": True}
        if url.startswith("sqlite"):
            kwargs["connect_args"] = {"check_same_thread": False}
        _engine = create_engine(url, **kwargs)
    return _engine


def reset_engine() -> None:
    """Drop the cached engine (used by tests after changing DATABASE_URL)."""
    global _engine
    if _engine is not None:
        _engine.dispose()
    _engine = None


def init_db() -> None:
    metadata.create_all(get_engine())


# ---------------------------------------------------------------- watchlist

def _watch_row(r) -> dict:
    return {"ticker": r.ticker, "name": r.name, "note": r.note, "added_at": _iso(r.added_at)}


def list_watchlist(active_only: bool = True) -> list[dict]:
    stmt = select(watchlist).order_by(watchlist.c.ticker)
    if active_only:
        stmt = stmt.where(watchlist.c.active.is_(True))
    with get_engine().connect() as conn:
        return [_watch_row(r) for r in conn.execute(stmt)]


def add_watchlist(ticker: str, name: str | None = None, note: str | None = None) -> dict:
    ticker = ticker.upper()
    with get_engine().begin() as conn:
        existing = conn.execute(select(watchlist).where(watchlist.c.ticker == ticker)).first()
        if existing:
            conn.execute(
                update(watchlist).where(watchlist.c.ticker == ticker).values(
                    active=True,
                    name=name if name is not None else existing.name,
                    note=note if note is not None else existing.note,
                )
            )
        else:
            count = conn.execute(
                select(func.count()).select_from(watchlist).where(watchlist.c.active.is_(True))
            ).scalar_one()
            if count >= cfg.MAX_WATCHLIST:
                raise ValueError(f"Watchlist is full ({cfg.MAX_WATCHLIST} tickers max)")
            conn.execute(insert(watchlist).values(
                ticker=ticker, name=name, note=note, active=True, added_at=utcnow()))
        row = conn.execute(select(watchlist).where(watchlist.c.ticker == ticker)).one()
    return _watch_row(row)


def remove_watchlist(ticker: str) -> bool:
    with get_engine().begin() as conn:
        res = conn.execute(delete(watchlist).where(watchlist.c.ticker == ticker.upper()))
        return res.rowcount > 0


# --------------------------------------------------------------------- runs

def try_start_run(trigger: str) -> int | None:
    """Create a 'running' row, or return None if a recent run is still in progress."""
    now = utcnow()
    cutoff = now - timedelta(minutes=cfg.RUN_STALE_MINUTES)
    with get_engine().begin() as conn:
        active = conn.execute(
            select(runs.c.id).where(and_(runs.c.status == "running", runs.c.started_at > cutoff))
        ).first()
        if active:
            return None
        conn.execute(
            update(runs)
            .where(and_(runs.c.status == "running", runs.c.started_at <= cutoff))
            .values(status="failed", finished_at=now, error="Marked failed: run never finished")
        )
        res = conn.execute(insert(runs).values(trigger=trigger, status="running", started_at=now))
        return res.inserted_primary_key[0]


def finish_run(run_id: int, status: str, summary: dict | None = None, error: str | None = None) -> None:
    with get_engine().begin() as conn:
        conn.execute(
            update(runs).where(runs.c.id == run_id).values(
                status=status,
                finished_at=utcnow(),
                summary=json.dumps(summary) if summary is not None else None,
                error=error,
            )
        )


def list_runs(limit: int = 10) -> list[dict]:
    stmt = select(runs).order_by(runs.c.id.desc()).limit(limit)
    with get_engine().connect() as conn:
        return [
            {
                "id": r.id, "trigger": r.trigger, "status": r.status,
                "started_at": _iso(r.started_at), "finished_at": _iso(r.finished_at),
                "summary": json.loads(r.summary) if r.summary else None, "error": r.error,
            }
            for r in conn.execute(stmt)
        ]


# ------------------------------------------------------------------- alerts

def last_alert_time(ticker: str) -> datetime | None:
    with get_engine().connect() as conn:
        return conn.execute(
            select(func.max(alerts.c.created_at)).where(alerts.c.ticker == ticker.upper())
        ).scalar_one()


def insert_alert(*, run_id, ticker, triggers, headline, summary, stance, confidence,
                 verified, price_at_alert, sent) -> int:
    with get_engine().begin() as conn:
        res = conn.execute(insert(alerts).values(
            run_id=run_id, ticker=ticker.upper(), created_at=utcnow(),
            triggers=json.dumps(triggers), headline=headline, summary=summary,
            stance=stance, confidence=confidence, verified=verified,
            price_at_alert=price_at_alert, sent=sent,
        ))
        return res.inserted_primary_key[0]


def _alert_row(r) -> dict:
    return {
        "id": r.id, "run_id": r.run_id, "ticker": r.ticker, "created_at": _iso(r.created_at),
        "triggers": json.loads(r.triggers) if r.triggers else [],
        "headline": r.headline, "summary": r.summary, "stance": r.stance,
        "confidence": r.confidence, "verified": r.verified,
        "price_at_alert": r.price_at_alert, "sent": r.sent,
        "outcome_at": _iso(r.outcome_at), "price_after": r.price_after,
        "return_pct": r.return_pct, "hit": r.hit,
    }


def list_alerts(limit: int = 20) -> list[dict]:
    stmt = select(alerts).order_by(alerts.c.id.desc()).limit(limit)
    with get_engine().connect() as conn:
        return [_alert_row(r) for r in conn.execute(stmt)]


def pending_outcome_alerts(created_before: datetime) -> list[dict]:
    stmt = select(alerts).where(and_(
        alerts.c.outcome_at.is_(None),
        alerts.c.price_at_alert.is_not(None),
        alerts.c.created_at <= created_before,
    ))
    with get_engine().connect() as conn:
        return [_alert_row(r) for r in conn.execute(stmt)]


def set_outcome(alert_id: int, price_after: float, return_pct: float, hit: bool | None) -> None:
    with get_engine().begin() as conn:
        conn.execute(update(alerts).where(alerts.c.id == alert_id).values(
            outcome_at=utcnow(), price_after=price_after, return_pct=return_pct, hit=hit))


def stats() -> dict:
    with get_engine().connect() as conn:
        rows = [_alert_row(r) for r in conn.execute(select(alerts))]
    scored = [r for r in rows if r["hit"] is not None]
    hits = sum(1 for r in scored if r["hit"])
    signed = [
        r["return_pct"] if r["stance"] == "bullish" else -r["return_pct"]
        for r in scored if r["return_pct"] is not None
    ]
    return {
        "alerts": len(rows),
        "verified": sum(1 for r in rows if r["verified"]),
        "scored": len(scored),
        "hits": hits,
        "hit_rate": round(hits / len(scored), 3) if scored else None,
        "avg_signed_return_pct": round(sum(signed) / len(signed), 2) if signed else None,
        "horizon_days": cfg.OUTCOME_HORIZON_DAYS,
    }
