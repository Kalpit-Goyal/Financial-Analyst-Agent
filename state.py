from typing import TypedDict, Annotated
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    company: str
    ticker: str
    messages: Annotated[list, add_messages]


def create_initial_state(company: str, messages: list, question: str, ticker: str = "") -> AgentState:
    """Create the initial agent state for a new analysis request."""
    return {
        "company": company,
        "ticker": ticker,
        "messages": messages + [{"role": "user", "content": question}],
    }