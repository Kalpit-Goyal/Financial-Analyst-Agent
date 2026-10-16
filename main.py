import json
import logging
import os
import asyncio
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Query, Request
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from langchain_core.messages import AIMessageChunk

from auth import get_current_user, router as auth_router
from graph import create_graph, close_graph
from history import router as history_router
from state import create_initial_state
from user_input import search_tickers
from monitor import db
from monitor.api import router as monitor_router
from monitor.db import init_db


# CORS: strip each origin
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",")]

# Rate limiting (limiter lives in ratelimit.py so routers can share it)
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from ratelimit import limiter


# Fail fast at startup
if not os.getenv("GROQ_API_KEY"):
    raise RuntimeError("GROQ_API_KEY is not configured. Set it in the .env file.")


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await asyncio.to_thread(init_db)
    except Exception:
        # Chat keeps working; history and the monitor endpoints need the database.
        logger.exception("database init failed; accounts, history and monitor are unavailable")
    yield
    await close_graph()


app = FastAPI(title="Financial Analyst Agent", lifespan=lifespan)

# Rate limiter setup
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type", "Authorization"],
)


app.include_router(auth_router)
app.include_router(history_router)
app.include_router(monitor_router)


class ChatTurn(BaseModel):
    role: str = Field(pattern=r"^(user|assistant)$")
    content: str = Field(max_length=20000)


class AnalysisRequest(BaseModel):
    company: str = Field(min_length=1, max_length=80)
    ticker: str = Field(pattern=r"^[A-Za-z0-9.\-^=]{1,15}$")
    question: str = Field(min_length=1, max_length=1000)
    messages: list[ChatTurn] = Field(default_factory=list, max_length=12)


@app.get("/")
def health_check():
    return {"status": "ok"}


@app.get("/resolve")
@limiter.limit("30/minute")
async def resolve(
    request: Request,
    q: str = Query(min_length=1, max_length=80),
    user: dict = Depends(get_current_user),
):
    results = await asyncio.to_thread(search_tickers, q)
    return {"results": results}


@app.post("/analyze")
@limiter.limit("10/minute")
async def analyze(
    request: Request,
    body: AnalysisRequest,
    user: dict = Depends(get_current_user),
):
    async def event_stream():
        conversation_id = None
        answer_parts: list[str] = []
        tool_names: list[str] = []
        error_text = None

        # History is best effort: chat must keep working even if the database is down.
        try:
            conversation_id = await asyncio.to_thread(
                db.upsert_conversation, user["id"], body.ticker, body.company)
            await asyncio.to_thread(
                db.add_message, conversation_id, "user", body.question)
        except Exception:
            logger.exception("could not record the conversation")
            conversation_id = None

        try:
            graph = await create_graph()

            initial_state = create_initial_state(
                company=body.company,
                messages=[t.model_dump() for t in body.messages],
                question=body.question,
                ticker=body.ticker,
            )

            reported_tool_calls: set = set()

            async for message_chunk, metadata in graph.astream(
                initial_state,
                config={
                    "tags": ["financial-analysis"],
                    "metadata": {
                        "company": body.company,
                        "question": body.question,
                    },
                    "recursion_limit": 50,
                },
                stream_mode="messages",
            ):
                if isinstance(message_chunk, AIMessageChunk):
                    content = message_chunk.content or ""

                    if content:
                        answer_parts.append(content)
                        yield json.dumps({
                            "type": "token",
                            "content": content,
                        }) + "\n"

                    tool_call_chunks = getattr(
                        message_chunk, "tool_call_chunks", None
                    )
                    if tool_call_chunks:
                        for chunk in tool_call_chunks:
                            tool_name = chunk.get("name")
                            if not tool_name:
                                continue

                            call_id = chunk.get("id")
                            dedupe_key = call_id or (tool_name, chunk.get("index", 0))
                            if dedupe_key in reported_tool_calls:
                                continue

                            reported_tool_calls.add(dedupe_key)
                            tool_names.append(tool_name)
                            yield json.dumps({
                                "type": "tool_call",
                                "tool": tool_name,
                            }) + "\n"

            yield json.dumps({
                "type": "done",
                "conversation_id": conversation_id,
            }) + "\n"
        except Exception:
            logger.exception("analysis failed")
            error_text = "Analysis failed. Please try again."
            yield json.dumps({
                "type": "error",
                "content": error_text,
            }) + "\n"
        finally:
            if conversation_id is not None:
                answer = "".join(answer_parts).strip()
                if error_text:
                    answer = (answer + "\n\n" if answer else "") + f"⚠️ {error_text}"
                if answer:
                    try:
                        await asyncio.to_thread(
                            db.add_message, conversation_id, "assistant", answer,
                            tool_names or None, error_text is not None)
                    except Exception:
                        logger.exception("could not save the assistant message")

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")
