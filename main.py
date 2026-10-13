import json
import logging
import os
import asyncio
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Request, Query
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from langchain_core.messages import AIMessageChunk

from graph import create_graph, close_graph
from state import create_initial_state
from user_input import search_tickers


ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",")

# Rate limiting
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)


# Fail fast at startup
if not os.getenv("GROQ_API_KEY"):
    raise RuntimeError("GROQ_API_KEY is not configured. Set it in the .env file.")


@asynccontextmanager
async def lifespan(app: FastAPI):
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
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


class ChatTurn(BaseModel):
    role: str = Field(pattern=r"^(user|assistant)$")
    content: str = Field(max_length=4000)


class AnalysisRequest(BaseModel):
    company: str = Field(min_length=1, max_length=80)
    ticker: str = Field(pattern=r"^[A-Za-z0-9.\-^=]{1,15}$")
    question: str = Field(min_length=1, max_length=1000)
    messages: list[ChatTurn] = Field(default_factory=list, max_length=12)


logger = logging.getLogger(__name__)


@app.get("/")
def health_check():
    return {"status": "ok"}


@app.get("/resolve")
async def resolve(q: str = Query(min_length=1, max_length=80)):
    results = await asyncio.to_thread(search_tickers, q)
    return {"results": results}


@app.post("/analyze")
@limiter.limit("10/minute")
async def analyze(request: Request, body: AnalysisRequest):
    async def event_stream():
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
                            yield json.dumps({
                                "type": "tool_call",
                                "tool": tool_name,
                            }) + "\n"

            yield json.dumps({"type": "done"}) + "\n"
        except Exception:
            logger.exception("analysis failed")
            yield json.dumps({
                "type": "error",
                "content": "Analysis failed. Please try again.",
            }) + "\n"

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")