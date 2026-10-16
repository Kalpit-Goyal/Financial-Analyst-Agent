"""HTTP API for the watchlist and monitor, scoped to the signed-in account.

Every endpoint requires a session token (Authorization: Bearer <token>) issued by
sign-in. Each account sees only its own watchlist, runs, alerts and stats.
"""
import asyncio

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from auth import get_current_user
from monitor import db
from monitor.runner import execute_run
from ratelimit import limiter


router = APIRouter()


class WatchlistAdd(BaseModel):
    ticker: str = Field(pattern=r"^[A-Za-z0-9.\-^=]{1,15}$")
    name: str | None = Field(default=None, max_length=120)
    note: str | None = Field(default=None, max_length=500)


@router.get("/watchlist")
@limiter.limit("30/minute")
async def get_watchlist(request: Request, user: dict = Depends(get_current_user)):
    return {"items": await asyncio.to_thread(db.list_watchlist, user["id"])}


@router.post("/watchlist", status_code=201)
@limiter.limit("30/minute")
async def add_to_watchlist(
    request: Request,
    body: WatchlistAdd,
    user: dict = Depends(get_current_user),
):
    try:
        item = await asyncio.to_thread(
            db.add_watchlist, user["id"], body.ticker, body.name, body.note)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return item


@router.delete("/watchlist/{ticker}")
@limiter.limit("30/minute")
async def remove_from_watchlist(
    request: Request,
    ticker: str,
    user: dict = Depends(get_current_user),
):
    if not await asyncio.to_thread(db.remove_watchlist, user["id"], ticker):
        raise HTTPException(status_code=404, detail="Ticker is not on the watchlist.")
    return {"removed": ticker.upper()}


@router.post("/monitor/run", status_code=202)
@limiter.limit("5/minute")
async def run_now(
    request: Request,
    background: BackgroundTasks,
    user: dict = Depends(get_current_user),
):
    run_id = await asyncio.to_thread(db.try_start_run, "manual", user["id"])
    if run_id is None:
        raise HTTPException(status_code=409, detail="A monitor run is already in progress.")
    background.add_task(execute_run, run_id)
    return {"run_id": run_id, "status": "running"}


@router.get("/monitor/runs")
@limiter.limit("60/minute")
async def get_runs(
    request: Request,
    limit: int = Query(10, ge=1, le=50),
    user: dict = Depends(get_current_user),
):
    return {"items": await asyncio.to_thread(db.list_runs, user["id"], limit)}


@router.get("/monitor/alerts")
@limiter.limit("60/minute")
async def get_alerts(
    request: Request,
    limit: int = Query(20, ge=1, le=100),
    user: dict = Depends(get_current_user),
):
    return {"items": await asyncio.to_thread(db.list_alerts, user["id"], limit)}


@router.get("/monitor/stats")
@limiter.limit("60/minute")
async def get_stats(request: Request, user: dict = Depends(get_current_user)):
    return await asyncio.to_thread(db.stats, user["id"])
