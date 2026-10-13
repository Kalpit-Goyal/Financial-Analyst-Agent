import os
import textwrap
from functools import lru_cache

from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage

from state import AgentState


load_dotenv()


@lru_cache(maxsize=1)
def get_llm():
    return ChatGroq(
        model=os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"),
        api_key=os.getenv("GROQ_API_KEY"),
    )


SYSTEM_PROMPT = textwrap.dedent("""
    You are a financial analyst assistant.

    Company: {company}
    Ticker: {ticker}

    Use the available financial tools whenever actual financial data is required.

    Do not invent financial information.
    Use the conversation history to understand context.

    Never repeat a tool call with the same arguments.
    You may call a statement tool once per period type (annual and quarterly).
    If a result contains "retryable": false, stop calling that tool and tell the user the data is unavailable.
    State the currency and period for every figure.
""")


def make_analyst_node(tools):
    llm = get_llm().bind_tools(tools)  # built once, not per call

    async def analyst_node(state: AgentState):
        prompt = SYSTEM_PROMPT.format(company=state["company"], ticker=state["ticker"])
        response = await llm.ainvoke([SystemMessage(content=prompt), *state["messages"]])
        return {"messages": [response]}

    return analyst_node


def make_final_answer_node():
    llm = get_llm()  # no tools bound

    async def final_answer_node(state: AgentState):
        prompt = SYSTEM_PROMPT.format(company=state["company"], ticker=state["ticker"])
        response = await llm.ainvoke([SystemMessage(content=prompt), *state["messages"]])
        return {"messages": [response]}

    return final_answer_node