import json
import os
import asyncio
from contextlib import asynccontextmanager
from urllib.request import urlopen

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from langchain_core.messages import AIMessageChunk

from graph import create_graph, close_graph


BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
KEEP_ALIVE_INTERVAL = int(os.getenv("KEEP_ALIVE_INTERVAL", "300"))


async def keep_alive():
    while True:
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: urlopen(BACKEND_URL, timeout=10),
            )
        except Exception:
            pass
        await asyncio.sleep(KEEP_ALIVE_INTERVAL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(keep_alive())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    await close_graph()


app = FastAPI(title="Financial Analyst Agent", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AnalysisRequest(BaseModel):
    company: str
    question: str
    messages: list = []


@app.get("/")
def health_check():
    return {"status": "ok"}


@app.post("/analyze")
async def analyze(request: AnalysisRequest):

    if not os.getenv("GROQ_API_KEY"):
        async def error_stream():
            yield json.dumps({
                "type": "error",
                "content": "GROQ_API_KEY is not configured. Set it in the .env file.",
            }) + "\n"
            yield json.dumps({"type": "done"}) + "\n"

        return StreamingResponse(error_stream(), media_type="application/x-ndjson")

    graph = await create_graph()

    initial_state = {
        "company": request.company,
        "ticker": "",
        "messages": request.messages + [
            {
                "role": "user",
                "content": request.question,
            }
        ],
        "financial_data": {},
        "web_data": {},
        "artifacts": {},
    }

    reported_tool_calls: set = set()

    async def event_stream():
        try:
            async for message_chunk, metadata in graph.astream(
                initial_state,
                config={
                    "tags": ["financial-analysis"],
                    "metadata": {
                        "company": request.company,
                        "question": request.question,
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
                                "content":
                                    f"\n\n*Calling {tool_name}...*\n\n",
                            }) + "\n"

            yield json.dumps({"type": "done"}) + "\n"
        except Exception as e:
            yield json.dumps({
                "type": "error",
                "content": str(e),
            }) + "\n"

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")
