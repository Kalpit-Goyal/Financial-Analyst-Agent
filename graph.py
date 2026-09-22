import sys
from pathlib import Path

from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_mcp_adapters.client import MultiServerMCPClient

from state import AgentState
from user_input import get_ticker
from analyst import analyst_node

SERVER_PATH = str(Path(__file__).resolve().parent / "mcp_server" / "financial_tools.py")


async def create_graph():

    client = MultiServerMCPClient(
        {
            "financial": {
                "command": sys.executable,
                "args": [SERVER_PATH],
                "transport": "stdio",
            }
        }
    )

    tools = await client.get_tools()

    graph = StateGraph(AgentState)

    graph.add_node("get_ticker", get_ticker)

    graph.add_node(
        "analyst",
        lambda state: analyst_node(state, tools)
    )

    graph.add_node(
        "tools",
        ToolNode(tools)
    )

    graph.add_edge(START, "get_ticker")
    graph.add_edge("get_ticker", "analyst")

    graph.add_conditional_edges(
        "analyst",
        tools_condition,
        {
            "tools": "tools",
            END: END,
        },
    )

    graph.add_edge("tools", "analyst")

    return graph.compile()