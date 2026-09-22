import os
from functools import lru_cache

from dotenv import load_dotenv
from langchain_groq import ChatGroq

from state import AgentState


load_dotenv()


@lru_cache(maxsize=1)
def get_llm():
    return ChatGroq(
        model=os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"),
        api_key=os.getenv("GROQ_API_KEY"),
    )


def analyst_node(state: AgentState, tools):

    llm = get_llm()
    llm_with_tools = llm.bind_tools(tools)

    response = llm_with_tools.invoke(
        [
            {
                "role": "system",
                "content": f"""
You are a financial analyst assistant.

Company: {state["company"]}
Ticker: {state["ticker"]}

Use the available financial tools whenever actual financial data is required.

Do not invent financial information.
Use the conversation history to understand context.
""",
            },
            *state["messages"],
        ]
    )

    return {"messages": [response]}
