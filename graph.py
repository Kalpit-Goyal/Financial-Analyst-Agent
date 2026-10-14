import asyncio
import os
import sys
from pathlib import Path
from typing import Literal

from langchain_core.messages import HumanMessage, ToolMessage
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode
from langchain_mcp_adapters.client import MultiServerMCPClient

from state import AgentState
from analyst import make_analyst_node, make_final_answer_node

SERVER_PATH = str(Path(__file__).resolve().parent / "mcp_server" / "financial_tools.py")
MCP_HOST = os.getenv("MCP_HOST", "127.0.0.1")
MCP_PORT = int(os.getenv("MCP_PORT", "8931"))
SERVER_STARTUP_TIMEOUT = float(os.getenv("MCP_STARTUP_TIMEOUT", "20"))

MAX_TOOL_CALLS = 8

_graph = None
_server = None
_lock = asyncio.Lock()


def _port_open() -> bool:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((MCP_HOST, MCP_PORT)) == 0


async def _start_server():
    env = {
        **os.environ,
        "MCP_TRANSPORT": "streamable-http",
        "MCP_HOST": MCP_HOST,
        "MCP_PORT": str(MCP_PORT),
    }
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        SERVER_PATH,
        env=env,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )

    loop = asyncio.get_running_loop()
    deadline = loop.time() + SERVER_STARTUP_TIMEOUT
    while loop.time() < deadline:
        if process.returncode is not None:
            return None
        if _port_open():
            return process
        await asyncio.sleep(0.25)
    return None


async def _create_client() -> MultiServerMCPClient:
    global _server

    _server = await _start_server()
    if _server is not None:
        return MultiServerMCPClient(
            {
                "financial": {
                    "url": f"http://{MCP_HOST}:{MCP_PORT}/mcp",
                    "transport": "streamable_http",
                }
            }
        )

    return MultiServerMCPClient(
        {
            "financial": {
                "command": sys.executable,
                "args": [SERVER_PATH],
                "transport": "stdio",
            }
        }
    )


def tools_used_this_turn(messages) -> int:
    n = 0
    for m in reversed(messages):
        if isinstance(m, HumanMessage):
            break
        if isinstance(m, ToolMessage):
            n += 1
    return n


def should_continue(state: AgentState) -> Literal["tools", "final_answer", END]:
    last = state["messages"][-1]
    if getattr(last, "tool_calls", None) and tools_used_this_turn(state["messages"]) < MAX_TOOL_CALLS:
        return "tools"
    if getattr(last, "tool_calls", None):
        return "final_answer"
    return END


async def create_graph():
    global _graph

    if _graph is not None:
        return _graph

    async with _lock:
        if _graph is not None:
            return _graph

        client = await _create_client()
        tools = await client.get_tools()

        graph = StateGraph(AgentState)

        analyst_node = make_analyst_node(tools)
        final_answer_node = make_final_answer_node()

        graph.add_node("analyst", analyst_node)

        graph.add_node(
            "tools",
            ToolNode(tools)
        )

        graph.add_node("final_answer", final_answer_node)

        graph.add_edge(START, "analyst")

        graph.add_conditional_edges(
            "analyst",
            should_continue,
            {
                "tools": "tools",
                "final_answer": "final_answer",
                END: END,
            },
        )

        graph.add_edge("tools", "analyst")

        graph.add_edge("final_answer", END)

        _graph = graph.compile()
        return _graph


async def close_graph() -> None:
    global _graph, _server

    _graph = None

    if _server is not None:
        _server.terminate()
        try:
            await asyncio.wait_for(_server.wait(), timeout=5)
        except (asyncio.TimeoutError, ProcessLookupError):
            _server.kill()
        _server = None