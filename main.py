import json
import os

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from langchain_core.messages import AIMessageChunk

from graph import create_graph


app = FastAPI(title="Financial Analyst Agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
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
                            if chunk.get("name"):
                                yield json.dumps({
                                    "type": "tool_call",
                                    "content":
                                        f"\n\n*Calling {chunk['name']}...*\n\n",
                                }) + "\n"

            yield json.dumps({"type": "done"}) + "\n"
        except Exception as e:
            yield json.dumps({
                "type": "error",
                "content": str(e),
            }) + "\n"

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")
