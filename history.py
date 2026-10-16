"""Chat history: list conversations, read one, delete one. Per signed-in account."""
import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from auth import get_current_user
from monitor import db
from ratelimit import limiter

router = APIRouter(prefix="/conversations", tags=["history"])


@router.get("")
@limiter.limit("60/minute")
async def list_conversations(
    request: Request,
    limit: int = Query(30, ge=1, le=100),
    user: dict = Depends(get_current_user),
):
    return {"items": await asyncio.to_thread(db.list_conversations, user["id"], limit)}


@router.get("/{conversation_id}")
@limiter.limit("60/minute")
async def get_conversation(
    request: Request,
    conversation_id: int,
    user: dict = Depends(get_current_user),
):
    owned = await asyncio.to_thread(db.conversation_owned, conversation_id, user["id"])
    if not owned:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    messages = await asyncio.to_thread(db.list_messages, conversation_id)
    return {"conversation_id": conversation_id, "messages": messages}


@router.delete("/{conversation_id}")
@limiter.limit("30/minute")
async def delete_conversation(
    request: Request,
    conversation_id: int,
    user: dict = Depends(get_current_user),
):
    removed = await asyncio.to_thread(db.delete_conversation, conversation_id, user["id"])
    if not removed:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return {"removed": conversation_id}
