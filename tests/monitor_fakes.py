"""Fakes that let the whole monitor loop run without Groq, Yahoo or Telegram."""
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from monitor.agents import Brief, Triage, TriageItem, Verdict


def make_signals(ticker, d1=6.0, d5=3.0, price=100.0, ok=True, days_to_earnings=None):
    if not ok:
        return {"ticker": ticker, "ok": False, "error": "no price data returned"}
    return {
        "ticker": ticker, "ok": True, "price": price, "currency": "USD", "as_of": "2026-10-13",
        "change_1d_pct": d1, "change_5d_pct": d5,
        "pct_from_52w_high": -10.0, "pct_from_52w_low": 40.0,
        "next_earnings": None, "days_to_earnings": days_to_earnings,
    }


def brief(headline="Margins expanded", stance="bullish", confidence="medium"):
    return Brief(
        headline=headline, summary="Revenue grew 20% YoY (USD, FY2025).", stance=stance,
        confidence=confidence, key_points=["Gross margin 70%"], risks=["Valuation"],
    )


def triage_all(*tickers, escalate=True):
    return Triage(decisions=[TriageItem(ticker=t, escalate=escalate, reason="test") for t in tickers])


class FakeStructured:
    def __init__(self, llm, schema):
        self.llm, self.schema = llm, schema

    async def ainvoke(self, messages):
        self.llm.calls.append((self.schema, messages))
        queue = self.llm.responses[self.schema]
        item = queue.pop(0) if len(queue) > 1 else queue[0]  # the last response repeats
        if isinstance(item, Exception):
            raise item
        return item


class FakeLLM:
    """responses: {Schema: [response, ...]}. Exceptions in the list are raised."""

    def __init__(self, responses):
        self.responses = {k: list(v) for k, v in responses.items()}
        self.calls = []

    def with_structured_output(self, schema):
        return FakeStructured(self, schema)

    def count(self, schema):
        return sum(1 for s, _ in self.calls if s is schema)


class FakeAnalystGraph:
    """Stands in for the chat graph: returns a draft plus one tool output as evidence."""

    def __init__(self, draft="Revenue grew 20% YoY.", evidence='{"revenue": 120, "prior": 100}', fail=None):
        self.draft, self.evidence, self.fail = draft, evidence, fail
        self.prompts = []

    async def ainvoke(self, state, config=None):
        self.prompts.append(state["messages"][-1]["content"])
        if self.fail:
            raise self.fail
        return {"messages": [
            HumanMessage(content=state["messages"][-1]["content"]),
            AIMessage(content="", tool_calls=[{"name": "get_financials", "args": {}, "id": "1"}]),
            ToolMessage(content=[{"type": "text", "text": self.evidence}], tool_call_id="1"),
            AIMessage(content=self.draft),
        ]}


class FakeNotifier:
    def __init__(self, ok=True):
        self.ok, self.sent = ok, []

    async def send(self, text):
        self.sent.append(text)
        return self.ok
