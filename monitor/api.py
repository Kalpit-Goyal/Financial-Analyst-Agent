"""Owner-only HTTP API for the watchlist and monitor.

Protected by a single OWNER_TOKEN (Authorization: Bearer <token>). If OWNER_TOKEN is
not set the endpoints are disabled, so a public deployment never exposes them by accident.
"""
import asyncio
import logging
import os
import secrets

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field

from monitor import db
from monitor.runner import execute_run
from ratelimit import limiter

logger = logging.getLogger(__name__)


def require_owner(authorization: str | None = Header(default=None)) -> None:
    expected = os.getenv("OWNER_TOKEN")
    if not expected:
        raise HTTPException(status_code=503, detail="Owner features are not configured on this server.")
    supplied = authorization[7:] if authorization and authorization.lower().startswith("bearer ") else ""
    if not secrets.compare_digest(supplied.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="Invalid access token.")


router = APIRouter(dependencies=[Depends(require_owner)])


class WatchlistAdd(BaseModel):
    ticker: str = Field(pattern=r"^[A-Za-z0-9.\-^=]{1,15}$")
    name: str | None = Field(default=None, max_length=120)
    note: str | None = Field(default=None, max_length=500)


@router.get("/watchlist")
@limiter.limit("30/minute")
async def get_watchlist(request: Request):
    return {"items": await asyncio.to_thread(db.list_watchlist)}


@router.post("/watchlist", status_code=201)
@limiter.limit("30/minute")
async def add_to_watchlist(request: Request, body: WatchlistAdd):
    try:
        item = await asyncio.to_thread(db.add_watchlist, body.ticker, body.name, body.note)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return item


@router.delete("/watchlist/{ticker}")
@limiter.limit("30/minute")
async def remove_from_watchlist(request: Request, ticker: str):
    if not await asyncio.to_thread(db.remove_watchlist, ticker):
        raise HTTPException(status_code=404, detail="Ticker is not on the watchlist.")
    return {"removed": ticker.upper()}


@router.post("/monitor/run", status_code=202)
@limiter.limit("5/minute")
async def run_now(request: Request, background: BackgroundTasks):
    run_id = await asyncio.to_thread(db.try_start_run, "manual")
    if run_id is None:
        raise HTTPException(status_code=409, detail="A monitor run is already in progress.")
    background.add_task(execute_run, run_id)
    return {"run_id": run_id, "status": "running"}


@router.get("/monitor/runs")
@limiter.limit("60/minute")
async def get_runs(request: Request, limit: int = Query(10, ge=1, le=50)):
    return {"items": await asyncio.to_thread(db.list_runs, limit)}


@router.get("/monitor/alerts")
@limiter.limit("60/minute")
async def get_alerts(request: Request, limit: int = Query(20, ge=1, le=100)):
    return {"items": await asyncio.to_thread(db.list_alerts, limit)}


@router.get("/monitor/stats")
@limiter.limit("60/minute")
async def get_stats(request: Request):
    return await asyncio.to_thread(db.stats)
