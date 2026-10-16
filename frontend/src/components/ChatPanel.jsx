import { useCallback, useEffect, useRef, useState } from "react";
import { api, streamAnalyze } from "../lib/api";
import MessageBubble from "./MessageBubble";
import { Badge, ErrorBanner, Icon, Spinner } from "./ui";

const SUGGESTIONS = [
  {
    icon: "trend",
    title: "Latest revenue",
    question: "What was the latest revenue and how did it change year over year?",
  },
  {
    icon: "chart",
    title: "Profitability",
    question: "What is the company's profitability and how are the margins trending?",
  },
  {
    icon: "shield",
    title: "Valuation",
    question: "What is the company's current valuation? Is it expensive versus its own history?",
  },
  {
    icon: "book",
    title: "Balance sheet",
    question: "Analyze the company's balance sheet: cash, debt and liquidity.",
  },
];

function toLocalMessage(message) {
  return {
    role: message.role,
    content: message.content,
    tools: message.tools || [],
    error: Boolean(message.error),
  };
}

export default function ChatPanel({ company, ticker, conversationId, onConversationCreated, onOpenMonitor }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [error, setError] = useState("");
  const loadedIdRef = useRef(null);
  const abortRef = useRef(null);
  const bottomRef = useRef(null);

  // Load a saved conversation when one is opened from the sidebar.
  useEffect(() => {
    if (!conversationId || loadedIdRef.current === conversationId) return undefined;
    loadedIdRef.current = conversationId;
    let cancelled = false;
    setHistoryLoading(true);
    setError("");
    api(`/conversations/${conversationId}`)
      .then((data) => {
        if (!cancelled) setMessages(data.messages.map(toLocalMessage));
      })
      .catch((err) => {
        if (!cancelled) setError(err.message);
      })
      .finally(() => {
        if (!cancelled) setHistoryLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [conversationId]);

  // Abort an in-flight answer when the user switches away.
  useEffect(() => {
    return () => abortRef.current?.abort();
  }, [conversationId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "auto" });
  }, [messages]);

  const updateLast = useCallback((fn) => {
    setMessages((prev) => {
      if (prev.length === 0) return prev;
      const next = [...prev];
      next[next.length - 1] = fn(next[next.length - 1]);
      return next;
    });
  }, []);

  const send = async (question) => {
    const text = (question ?? input).trim();
    if (!text || busy) return;

    const history = messages
      .filter((m) => m.content && !m.error)
      .slice(-10)
      .map(({ role, content }) => ({ role, content }));

    setMessages((prev) => [
      ...prev,
      { role: "user", content: text },
      { role: "assistant", content: "", tools: [] },
    ]);
    setInput("");
    setError("");
    setBusy(true);
    abortRef.current = new AbortController();

    try {
      await streamAnalyze(
        { company, ticker, question: text, messages: history },
        {
          signal: abortRef.current.signal,
          onEvent: (event) => {
            if (event.type === "tool_call") {
              updateLast((last) => ({
                ...last,
                tools: [...new Set([...(last.tools || []), event.tool])],
              }));
            } else if (event.type === "token") {
              updateLast((last) => ({ ...last, content: (last.content || "") + event.content }));
            } else if (event.type === "error") {
              updateLast((last) => ({
                ...last,
                content: (last.content ? `${last.content}\n\n` : "") + `⚠️ ${event.content}`,
                error: true,
              }));
            } else if (event.type === "done" && event.conversation_id) {
              loadedIdRef.current = event.conversation_id;
              onConversationCreated?.(event.conversation_id);
            }
          },
        }
      );
    } catch (err) {
      if (err?.name !== "AbortError") {
        updateLast((last) => ({
          ...last,
          content: (last.content ? `${last.content}\n\n` : "") + `⚠️ ${err.message}`,
          error: true,
        }));
      }
    } finally {
      setBusy(false);
      abortRef.current = null;
    }
  };

  const cancel = () => {
    abortRef.current?.abort();
    setBusy(false);
  };

  const onKeyDown = (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      send();
    }
  };

  const lines = input.split("\n").length;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="flex items-center gap-3 border-b border-white/[0.06] px-5 py-4 sm:px-8">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h2 className="truncate text-base font-semibold text-white">{company}</h2>
            <Badge tone="indigo">{ticker}</Badge>
          </div>
          <p className="mt-0.5 text-xs text-slate-500">
            Grounded in live Yahoo Finance data · tools are shown on every answer
          </p>
        </div>
        {onOpenMonitor && (
          <button type="button" onClick={onOpenMonitor} className="btn-ghost ml-auto hidden sm:inline-flex">
            <Icon name="activity" className="h-4 w-4" />
            Monitor
          </button>
        )}
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto max-w-3xl space-y-5 px-5 py-8 sm:px-8">
          {historyLoading ? (
            <div className="flex items-center justify-center gap-2 py-24 text-sm text-slate-400">
              <Spinner /> Loading conversation…
            </div>
          ) : messages.length === 0 ? (
            <div className="animate-fade-up pt-6">
              <div className="text-center">
                <span className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl border border-white/10 bg-white/[0.04] text-indigo-300">
                  <Icon name="spark" className="h-6 w-6" />
                </span>
                <h2 className="mt-5 text-2xl font-semibold text-white">Ask about {company}</h2>
                <p className="mx-auto mt-2 max-w-lg text-sm leading-6 text-slate-400">
                  Revenue, margins, debt, cash flow, valuation — the analyst fetches the numbers before it
                  answers, and every tool call is visible.
                </p>
              </div>
              <div className="mt-8 grid gap-3 sm:grid-cols-2">
                {SUGGESTIONS.map((suggestion) => (
                  <button
                    key={suggestion.title}
                    type="button"
                    onClick={() => send(suggestion.question)}
                    className="panel panel-hover flex items-start gap-3 p-4 text-left"
                  >
                    <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-white/10 bg-white/[0.04] text-indigo-300">
                      <Icon name={suggestion.icon} className="h-4 w-4" />
                    </span>
                    <span>
                      <span className="block text-sm font-medium text-slate-200">{suggestion.title}</span>
                      <span className="mt-0.5 block text-xs leading-5 text-slate-500">{suggestion.question}</span>
                    </span>
                  </button>
                ))}
              </div>
            </div>
          ) : (
            messages.map((message, index) => (
              <MessageBubble
                key={index}
                role={message.role}
                content={message.content}
                tools={message.tools}
                error={message.error}
                streaming={busy && index === messages.length - 1 && message.role === "assistant"}
              />
            ))
          )}
          {!historyLoading && messages.length === 0 && error && (
            <div className="mx-auto max-w-lg">
              <ErrorBanner>{error}</ErrorBanner>
            </div>
          )}
          <div ref={bottomRef} />
        </div>
      </div>

      <div className="border-t border-white/[0.06] px-5 py-4 sm:px-8">
        <div className="mx-auto max-w-3xl">
          {messages.length > 0 && error && (
            <div className="mb-3">
              <ErrorBanner>{error}</ErrorBanner>
            </div>
          )}
          <div className="relative">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={onKeyDown}
              placeholder={`Ask about ${company}…`}
              rows={Math.min(lines, 5)}
              aria-label="Ask a question about the company"
              className="w-full resize-none rounded-2xl border border-white/10 bg-white/[0.03] py-3.5 pl-4 pr-14 text-sm text-slate-100 placeholder-slate-500 outline-none transition focus:border-indigo-400/70 focus:ring-2 focus:ring-indigo-500/20"
            />
            {busy ? (
              <button
                type="button"
                onClick={cancel}
                aria-label="Cancel answer"
                className="absolute bottom-3 right-3 flex h-9 w-9 items-center justify-center rounded-xl border border-rose-400/30 bg-rose-500/15 text-rose-300 transition hover:bg-rose-500/25"
              >
                <Icon name="stop" className="h-4 w-4" />
              </button>
            ) : (
              <button
                type="button"
                onClick={() => send()}
                disabled={!input.trim()}
                aria-label="Send question"
                className="absolute bottom-3 right-3 flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-r from-indigo-500 to-violet-500 text-white shadow-lg shadow-indigo-950/40 transition hover:from-indigo-400 hover:to-violet-400 disabled:from-slate-700 disabled:to-slate-700 disabled:text-slate-500 disabled:shadow-none"
              >
                <Icon name="arrowUp" className="h-4 w-4" />
              </button>
            )}
          </div>
          <p className="mt-2 text-center text-[11px] text-slate-600">
            Enter sends · Shift+Enter adds a line · answers are saved to your history
          </p>
        </div>
      </div>
    </div>
  );
}
