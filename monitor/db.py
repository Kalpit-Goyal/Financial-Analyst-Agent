"""Persistence for accounts, chat history, and the monitor.

Uses SQLAlchemy Core so the same code runs on SQLite (local dev) and Postgres
(set DATABASE_URL, e.g. a free Neon database, so data survives redeploys).
All functions are synchronous; call them with asyncio.to_thread from async code.
"""
import json
import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import (
    Boolean, Column, DateTime, Float, Integer, MetaData, String, Table, Text,
    UniqueConstraint, and_, create_engine, delete, func, insert, inspect,
    select, text, update,
)

from monitor import config as cfg

metadata = MetaData()

# ------------------------------------------------------------------ accounts

users = Table(
    "users", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("email", String(160), nullable=False, unique=True),
    Column("name", String(80)),
    Column("password_hash", String(255), nullable=False),
    Column("created_at", DateTime, nullable=False),
)

sessions = Table(
    "sessions", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("token_hash", String(64), nullable=False, unique=True),
    Column("user_id", Integer, nullable=False),
    Column("created_at", DateTime, nullable=False),
    Column("expires_at", DateTime, nullable=False),
)

# --------------------------------------------------------------- watchlist

watchlist = Table(
    "watchlist", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", Integer, nullable=False),
    Column("ticker", String(20), nullable=False),
    Column("name", String(120)),
    Column("note", Text),
    Column("active", Boolean, nullable=False, default=True),
    Column("added_at", DateTime, nullable=False),
    UniqueConstraint("user_id", "ticker", name="uq_watchlist_user_ticker"),
)

runs = Table(
    "runs", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", Integer),  # NULL = scheduled / system run
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
    Column("user_id", Integer),  # the account that watches this ticker
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

# ------------------------------------------------------------- chat history

conversations = Table(
    "conversations", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", Integer, nullable=False),
    Column("ticker", String(20), nullable=False),
    Column("company", String(120)),
    Column("created_at", DateTime, nullable=False),
    Column("updated_at", DateTime, nullable=False),
    UniqueConstraint("user_id", "ticker", name="uq_conversations_user_ticker"),
)

messages = Table(
    "messages", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("conversation_id", Integer, nullable=False),
    Column("role", String(16), nullable=False),  # user | assistant
    Column("content", Text, nullable=False),
    Column("tools", Text),                       # JSON list of tool names
    Column("error", Boolean, nullable=False, default=False),
    Column("created_at", DateTime, nullable=False),
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
    engine = get_engine()
    _drop_legacy_watchlist(engine)
    metadata.create_all(engine)
    _add_user_columns(engine)


def _drop_legacy_watchlist(engine) -> None:
    """Pre-accounts databases had one global watchlist with a unique ticker.

    That schema cannot express per-user lists, so it is rebuilt. The old rows
    belonged to no account (there were none), so nothing is copied over.
    """
    inspector = inspect(engine)
    if "watchlist" not in inspector.get_table_names():
        return
    columns = {c["name"] for c in inspector.get_columns("watchlist")}
    if "user_id" not in columns:
        watchlist.drop(engine, checkfirst=True)


def _add_user_columns(engine) -> None:
    """Add runs.user_id / alerts.user_id to databases created before accounts."""
    inspector = inspect(engine)
    names = inspector.get_table_names()
    for table in (runs, alerts):
        if table.name in names and "user_id" not in {c["name"] for c in inspector.get_columns(table.name)}:
            with engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE {table.name} ADD COLUMN user_id INTEGER"))


# ------------------------------------------------------------------ accounts

def _user_row(u) -> dict:
    return {"id": u.id, "email": u.email, "name": u.name, "created_at": _iso(u.created_at)}


def create_user(email: str, name: str | None, password_hash: str) -> dict:
    email = email.strip().lower()
    with get_engine().begin() as conn:
        if conn.execute(select(users.c.id).where(users.c.email == email)).first():
            raise ValueError("An account with that email already exists.")
        res = conn.execute(insert(users).values(
            email=email, name=name, password_hash=password_hash, created_at=utcnow()))
        row = conn.execute(select(users).where(users.c.id == res.inserted_primary_key[0])).one()
    return _user_row(row)


def get_user_by_email(email: str):
    email = email.strip().lower()
    with get_engine().connect() as conn:
        row = conn.execute(select(users).where(users.c.email == email)).first()
    return {**_user_row(row), "password_hash": row.password_hash} if row else None


def get_user(user_id: int) -> dict | None:
    with get_engine().connect() as conn:
        row = conn.execute(select(users).where(users.c.id == user_id)).first()
    return _user_row(row) if row else None


def create_session(user_id: int, token_hash: str, ttl_days: int) -> None:
    now = utcnow()
    with get_engine().begin() as conn:
        conn.execute(delete(sessions).where(sessions.c.expires_at < now))
        conn.execute(insert(sessions).values(
            token_hash=token_hash, user_id=user_id,
            created_at=now, expires_at=now + timedelta(days=ttl_days)))


def user_for_session(token_hash: str) -> dict | None:
    with get_engine().connect() as conn:
        row = conn.execute(
            select(users)
            .select_from(sessions.join(users, sessions.c.user_id == users.c.id))
            .where(and_(sessions.c.token_hash == token_hash, sessions.c.expires_at > utcnow()))
        ).first()
    return _user_row(row) if row else None


def delete_session(token_hash: str) -> None:
    with get_engine().begin() as conn:
        conn.execute(delete(sessions).where(sessions.c.token_hash == token_hash))


# ---------------------------------------------------------------- watchlist

def _watch_row(r) -> dict:
    return {"ticker": r.ticker, "name": r.name, "note": r.note,
            "added_at": _iso(r.added_at), "user_id": r.user_id}


def list_watchlist(user_id: int | None = None, active_only: bool = True) -> list[dict]:
    """Rows for one account, or every account when user_id is None (scheduled scans)."""
    stmt = select(watchlist).order_by(watchlist.c.ticker)
    if user_id is not None:
        stmt = stmt.where(watchlist.c.user_id == user_id)
    if active_only:
        stmt = stmt.where(watchlist.c.active.is_(True))
    with get_engine().connect() as conn:
        return [_watch_row(r) for r in conn.execute(stmt)]


def add_watchlist(user_id: int, ticker: str, name: str | None = None, note: str | None = None) -> dict:
    ticker = ticker.upper()
    with get_engine().begin() as conn:
        existing = conn.execute(
            select(watchlist).where(and_(
                watchlist.c.user_id == user_id, watchlist.c.ticker == ticker))).first()
        if existing:
            conn.execute(
                update(watchlist).where(watchlist.c.id == existing.id).values(
                    active=True,
                    name=name if name is not None else existing.name,
                    note=note if note is not None else existing.note,
                )
            )
        else:
            count = conn.execute(
                select(func.count()).select_from(watchlist).where(and_(
                    watchlist.c.user_id == user_id, watchlist.c.active.is_(True)))
            ).scalar_one()
            if count >= cfg.MAX_WATCHLIST:
                raise ValueError(f"Watchlist is full ({cfg.MAX_WATCHLIST} tickers max)")
            conn.execute(insert(watchlist).values(
                user_id=user_id, ticker=ticker, name=name, note=note,
                active=True, added_at=utcnow()))
        row = conn.execute(
            select(watchlist).where(and_(
                watchlist.c.user_id == user_id, watchlist.c.ticker == ticker))).one()
    return _watch_row(row)


def remove_watchlist(user_id: int, ticker: str) -> bool:
    with get_engine().begin() as conn:
        res = conn.execute(delete(watchlist).where(and_(
            watchlist.c.user_id == user_id, watchlist.c.ticker == ticker.upper())))
        return res.rowcount > 0


# --------------------------------------------------------------------- runs

def try_start_run(trigger: str, user_id: int | None = None) -> int | None:
    """Create a 'running' row, or return None if a recent run is still in progress.

    Only one run (manual or scheduled) happens at a time so the shared LLM
    quota and the data source are not hammered from two directions.
    """
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
        res = conn.execute(insert(runs).values(
            user_id=user_id, trigger=trigger, status="running", started_at=now))
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


def _run_row(r) -> dict:
    return {
        "id": r.id, "user_id": r.user_id, "trigger": r.trigger, "status": r.status,
        "started_at": _iso(r.started_at), "finished_at": _iso(r.finished_at),
        "summary": json.loads(r.summary) if r.summary else None, "error": r.error,
    }


def get_run(run_id: int) -> dict | None:
    with get_engine().connect() as conn:
        row = conn.execute(select(runs).where(runs.c.id == run_id)).first()
    return _run_row(row) if row else None


def list_runs(user_id: int | None = None, limit: int = 10) -> list[dict]:
    stmt = select(runs).order_by(runs.c.id.desc()).limit(limit)
    if user_id is not None:
        stmt = stmt.where(runs.c.user_id == user_id)
    with get_engine().connect() as conn:
        return [_run_row(r) for r in conn.execute(stmt)]


# ------------------------------------------------------------------- alerts

def last_alert_time(ticker: str, user_id: int | None = None) -> datetime | None:
    """Most recent alert for a ticker. Filtered to one account when user_id is given."""
    stmt = select(func.max(alerts.c.created_at)).where(alerts.c.ticker == ticker.upper())
    if user_id is not None:
        stmt = stmt.where(alerts.c.user_id == user_id)
    with get_engine().connect() as conn:
        return conn.execute(stmt).scalar_one()


def insert_alert(*, run_id, ticker, triggers, headline, summary, stance, confidence,
                 verified, price_at_alert, sent, user_id=None) -> int:
    with get_engine().begin() as conn:
        res = conn.execute(insert(alerts).values(
            run_id=run_id, user_id=user_id, ticker=ticker.upper(), created_at=utcnow(),
            triggers=json.dumps(triggers), headline=headline, summary=summary,
            stance=stance, confidence=confidence, verified=verified,
            price_at_alert=price_at_alert, sent=sent,
        ))
        return res.inserted_primary_key[0]


def _alert_row(r) -> dict:
    return {
        "id": r.id, "run_id": r.run_id, "user_id": r.user_id, "ticker": r.ticker,
        "created_at": _iso(r.created_at),
        "triggers": json.loads(r.triggers) if r.triggers else [],
        "headline": r.headline, "summary": r.summary, "stance": r.stance,
        "confidence": r.confidence, "verified": r.verified,
        "price_at_alert": r.price_at_alert, "sent": r.sent,
        "outcome_at": _iso(r.outcome_at), "price_after": r.price_after,
        "return_pct": r.return_pct, "hit": r.hit,
    }


def list_alerts(user_id: int | None = None, limit: int = 20) -> list[dict]:
    stmt = select(alerts).order_by(alerts.c.id.desc()).limit(limit)
    if user_id is not None:
        stmt = stmt.where(alerts.c.user_id == user_id)
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


def stats(user_id: int | None = None) -> dict:
    stmt = select(alerts)
    if user_id is not None:
        stmt = stmt.where(alerts.c.user_id == user_id)
    with get_engine().connect() as conn:
        rows = [_alert_row(r) for r in conn.execute(stmt)]
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


# --------------------------------------------------------------- chat history

def upsert_conversation(user_id: int, ticker: str, company: str | None) -> int:
    """One conversation per account and ticker; returns its id."""
    ticker = ticker.upper()
    now = utcnow()
    with get_engine().begin() as conn:
        existing = conn.execute(
            select(conversations).where(and_(
                conversations.c.user_id == user_id, conversations.c.ticker == ticker))).first()
        if existing:
            conn.execute(update(conversations).where(conversations.c.id == existing.id).values(
                company=company or existing.company, updated_at=now))
            return existing.id
        res = conn.execute(insert(conversations).values(
            user_id=user_id, ticker=ticker, company=company,
            created_at=now, updated_at=now))
        return res.inserted_primary_key[0]


def add_message(conversation_id: int, role: str, content: str,
                tools: list[str] | None = None, error: bool = False) -> int:
    now = utcnow()
    with get_engine().begin() as conn:
        res = conn.execute(insert(messages).values(
            conversation_id=conversation_id, role=role, content=content,
            tools=json.dumps(tools) if tools else None, error=error, created_at=now))
        conn.execute(update(conversations).where(conversations.c.id == conversation_id).values(
            updated_at=now))
        return res.inserted_primary_key[0]


def _message_row(m) -> dict:
    return {
        "id": m.id, "role": m.role, "content": m.content,
        "tools": json.loads(m.tools) if m.tools else [],
        "error": m.error, "created_at": _iso(m.created_at),
    }


def conversation_owned(conversation_id: int, user_id: int) -> bool:
    with get_engine().connect() as conn:
        row = conn.execute(select(conversations.c.id).where(and_(
            conversations.c.id == conversation_id,
            conversations.c.user_id == user_id))).first()
    return row is not None


def list_conversations(user_id: int, limit: int = 30) -> list[dict]:
    with get_engine().connect() as conn:
        rows = conn.execute(
            select(conversations).where(conversations.c.user_id == user_id)
            .order_by(conversations.c.updated_at.desc()).limit(limit)).all()
        ids = [r.id for r in rows]
        counts, previews = {}, {}
        if ids:
            counts = dict(conn.execute(
                select(messages.c.conversation_id, func.count(messages.c.id))
                .where(messages.c.conversation_id.in_(ids))
                .group_by(messages.c.conversation_id)).all())
            last_ids = dict(conn.execute(
                select(messages.c.conversation_id, func.max(messages.c.id))
                .where(messages.c.conversation_id.in_(ids))
                .group_by(messages.c.conversation_id)).all())
            for conversation_id, message_id in last_ids.items():
                previews[conversation_id] = conn.execute(
                    select(messages.c.content).where(messages.c.id == message_id)).scalar_one()
    return [
        {
            "id": r.id, "ticker": r.ticker, "company": r.company,
            "created_at": _iso(r.created_at), "updated_at": _iso(r.updated_at),
            "message_count": counts.get(r.id, 0),
            "preview": (previews.get(r.id) or "")[:160],
        }
        for r in rows
    ]


def list_messages(conversation_id: int, limit: int = 500) -> list[dict]:
    stmt = (select(messages).where(messages.c.conversation_id == conversation_id)
            .order_by(messages.c.id.asc()).limit(limit))
    with get_engine().connect() as conn:
        return [_message_row(m) for m in conn.execute(stmt)]


def delete_conversation(conversation_id: int, user_id: int) -> bool:
    with get_engine().begin() as conn:
        owned = conn.execute(select(conversations.c.id).where(and_(
            conversations.c.id == conversation_id,
            conversations.c.user_id == user_id))).first()
        if not owned:
            return False
        conn.execute(delete(messages).where(messages.c.conversation_id == conversation_id))
        conn.execute(delete(conversations).where(conversations.c.id == conversation_id))
        return True
