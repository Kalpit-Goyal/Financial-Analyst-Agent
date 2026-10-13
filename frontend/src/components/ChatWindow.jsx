import { useState, useRef, useEffect, useCallback } from "react";
import ChatMessage from "./ChatMessage";

const SUGGESTIONS = [
  { title: "Latest revenue", subtitle: "Analyze recent revenue", question: "What was the latest revenue?" },
  { title: "Profitability", subtitle: "Analyze profit and margins", question: "What is the company's profitability?" },
  { title: "Valuation", subtitle: "Analyze valuation metrics", question: "What is the company's current valuation?" },
  { title: "Balance sheet", subtitle: "Analyze assets and liabilities", question: "Analyze the company's balance sheet." },
];

function ChatWindow({ company, ticker }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef(null);
  const abortControllerRef = useRef(null);

  const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

  const scrollToBottom = useCallback((behavior = "smooth") => {
    messagesEndRef.current?.scrollIntoView({ behavior });
  }, []);

  useEffect(() => {
    scrollToBottom("auto");
  }, [messages, scrollToBottom]);

  const updateLastMessage = useCallback((fn) => {
    setMessages((prev) => {
      if (prev.length === 0) return prev;
      const newMessages = [...prev];
      newMessages[newMessages.length - 1] = fn(newMessages[newMessages.length - 1]);
      return newMessages;
    });
  }, []);

  const sendMessage = async () => {
    if (!input.trim() || loading) {
      return;
    }

    const userMessage = input.trim();

    setInput("");

    setMessages((prev) => [
      ...prev,
      { role: "user", content: userMessage },
      { role: "assistant", content: "", tools: [] },
    ]);

    setLoading(true);
    abortControllerRef.current = new AbortController();

    try {
      const response = await fetch(
        `${API_URL}/analyze`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            company: company,
            ticker: ticker || "",
            question: userMessage,
            messages: messages
              .filter((m) => m.content && !m.error)
              .slice(-10)
              .map(({ role, content }) => ({ role, content })),
          }),
          signal: abortControllerRef.current.signal,
        }
      );

      if (!response.ok) {
        if (response.status === 429) {
          throw new Error("Too many requests. Please wait a moment and try again.");
        }
        throw new Error(`Backend returned ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (!line.trim()) continue;

          let event;
          try {
            event = JSON.parse(line);
          } catch {
            continue;
          }

          if (event.type === "tool_call") {
            updateLastMessage((last) => ({
              ...last,
              tools: [...(last.tools || []), event.tool],
            }));
          } else if (event.type === "token") {
            updateLastMessage((last) => ({
              ...last,
              content: (last.content || "") + event.content,
            }));
          } else if (event.type === "error") {
            updateLastMessage((last) => ({
              ...last,
              content: (last.content ? last.content + "\n\n" : "") + `⚠️ ${event.content}`,
              error: true,
            }));
          }
        }
      }
    } catch (error) {
      if (error.name === "AbortError") return;
      console.error("Chat error:", error);

      updateLastMessage((last) => ({
        ...last,
        content: (last.content ? last.content + "\n\n" : "") + `⚠️ ${error.message}`,
        error: true,
      }));
    } finally {
      setLoading(false);
      abortControllerRef.current = null;
    }
  };

  const handleCancel = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      setLoading(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const handleSuggestion = (question) => {
    setInput(question);
  };

  return (
    <div className="min-h-screen bg-white text-gray-900 flex">
      {/* Sidebar */}
      <aside className="hidden md:flex w-64 bg-white border-r border-gray-200 flex-col">
        {/* Application title */}
        <div className="p-5 border-b border-gray-200">
          <h1 className="font-semibold text-lg">
            Financial Analyst
          </h1>
          <p className="text-xs text-gray-500 mt-1">
            AI Financial Research
          </p>
        </div>

        {/* Company */}
        <div className="p-5">
          <p className="text-xs uppercase tracking-wider text-gray-500">
            Analyzing
          </p>
          <h2 className="text-lg font-semibold mt-2">
            {company} {ticker && `(${ticker})`}
          </h2>
        </div>

        {/* Capabilities */}
        <div className="px-5 mt-3">
          <p className="text-xs uppercase tracking-wider text-gray-500 mb-3">
            Capabilities
          </p>
          <div className="space-y-2">
            <div className="text-sm text-gray-700 px-3 py-2 rounded-lg bg-gray-100">
              Financial Analysis
            </div>
            <div className="text-sm text-gray-400 px-3 py-2 rounded-lg">
              Web Research
            </div>
            <div className="text-sm text-gray-400 px-3 py-2 rounded-lg">
              Charts
            </div>
            <div className="text-sm text-gray-400 px-3 py-2 rounded-lg">
              Predictions
            </div>
            <div className="text-sm text-gray-400 px-3 py-2 rounded-lg">
              Reports
            </div>
          </div>
        </div>
      </aside>

      {/* Main */}
      <main className="flex-1 flex flex-col min-w-0">
        {/* Header */}
        <header className="h-16 border-b border-gray-200 flex items-center px-6">
          <div>
            <h2 className="font-semibold">
              {company} {ticker && `(${ticker})`}
            </h2>
            <p className="text-xs text-gray-500">
              Financial Analysis
            </p>
          </div>
        </header>

        {/* Conversation */}
        <div className="flex-1 overflow-y-auto">
          <div className="max-w-3xl mx-auto px-6 py-10">
            {/* Empty state */}
            {messages.length === 0 && (
              <div className="text-center pt-16">
                <div className="text-4xl mb-5">
                  <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#3b82f6" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M3 3v18h18"/>
                    <path d="M7 16l4-4 4 4 5-5"/>
                    <circle cx="7" cy="16" r="1.5" fill="#3b82f6" stroke="none"/>
                    <circle cx="11" cy="12" r="1.5" fill="#3b82f6" stroke="none"/>
                    <circle cx="15" cy="16" r="1.5" fill="#3b82f6" stroke="none"/>
                    <circle cx="20" cy="11" r="1.5" fill="#3b82f6" stroke="none"/>
                  </svg>
                </div>
                <h2 className="text-2xl font-semibold">
                  Ask about {company}
                </h2>
                <p className="text-gray-500 mt-3 max-w-lg mx-auto">
                  Ask questions about revenue, profitability,
                  valuation, balance sheet, cash flow, or
                  any other financial information.
                </p>
                {/* Suggestions */}
                <div className="grid sm:grid-cols-2 gap-3 mt-8 text-left">
                  {SUGGESTIONS.map((s) => (
                    <button
                      key={s.title}
                      onClick={() => handleSuggestion(s.question)}
                      className="border border-gray-200 bg-white rounded-xl p-4 hover:border-gray-300 transition text-left"
                    >
                      <p className="text-sm font-medium">{s.title}</p>
                      <p className="text-xs text-gray-500 mt-1">{s.subtitle}</p>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Messages */}
            {messages.length > 0 && (
              <div className="space-y-6">
                {messages.map((message, index) => (
                  <ChatMessage
                    key={index}
                    role={message.role}
                    content={message.content}
                    tools={message.tools}
                    error={message.error}
                  />
                ))}

                {/* Loading indicator */}
                {(loading || (messages.at(-1)?.tools && messages.at(-1)?.tools.length > 0)) && (
                  <div className="flex justify-start">
                    <div className="bg-white border border-gray-200 rounded-2xl px-5 py-4">
                      <div className="flex gap-1">
                        <span className="w-2 h-2 bg-gray-500 rounded-full animate-bounce" />
                        <span className="w-2 h-2 bg-gray-500 rounded-full animate-bounce [animation-delay:150ms]" />
                        <span className="w-2 h-2 bg-gray-500 rounded-full animate-bounce [animation-delay:300ms]" />
                      </div>
                    </div>
                  </div>
                )}

                <div ref={messagesEndRef} />
              </div>
            )}
          </div>
        </div>

        {/* Input */}
        <div className="border-t border-gray-200 bg-white p-4">
          <div className="max-w-3xl mx-auto">
            <div className="relative">
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={`Ask about ${company}...`}
                rows={1}
                aria-label="Ask a question about the company"
                className="w-full resize-none bg-white border border-gray-300 rounded-2xl px-5 py-4 pr-14 outline-none focus:border-blue-500 transition"
              />
              {loading ? (
                <button
                  onClick={handleCancel}
                  aria-label="Cancel request"
                  className="absolute right-3 bottom-3 h-9 w-9 rounded-xl bg-red-100 hover:bg-red-200 text-red-600 flex items-center justify-center transition"
                >
                  ✕
                </button>
              ) : (
                <button
                  onClick={sendMessage}
                  disabled={!input.trim()}
                  aria-label="Send message"
                  className="absolute right-3 bottom-3 h-9 w-9 rounded-xl bg-blue-600 hover:bg-blue-500 disabled:bg-gray-100 disabled:text-gray-400 flex items-center justify-center transition"
                >
                  ↑
                </button>
              )}
            </div>
            <p className="text-center text-xs text-gray-400 mt-2">
              AI-generated financial analysis may contain errors.
            </p>
          </div>
        </div>
      </main>
    </div>
  );
}

export default ChatWindow;