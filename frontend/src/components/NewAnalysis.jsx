import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { formatTime } from "../lib/format";
import { EmptyState, ErrorBanner, Icon, Spinner } from "./ui";

function useTickerSearch(query) {
  const [results, setResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    const timer = setTimeout(async () => {
      const trimmed = query.trim();
      if (trimmed.length < 2) {
        if (!cancelled) {
          setResults([]);
          setSearching(false);
        }
        return;
      }
      setSearching(true);
      try {
        const data = await api(`/resolve?q=${encodeURIComponent(trimmed)}`);
        if (!cancelled) {
          setResults(data.results || []);
          setError("");
        }
      } catch (err) {
        if (!cancelled) {
          setResults([]);
          setError(err.message);
        }
      } finally {
        if (!cancelled) setSearching(false);
      }
    }, 350);

    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [query]);

  return { results, searching, error };
}

export default function NewAnalysis({ onSubmit, conversations = [], onOpenConversation }) {
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState(null);
  const { results, searching, error } = useTickerSearch(query);

  const start = (event) => {
    event.preventDefault();
    if (selected) onSubmit(selected.name, selected.symbol);
  };

  return (
    <div className="mx-auto flex h-full max-w-3xl flex-col justify-center px-5 py-10 sm:px-8">
      <div className="animate-fade-up">
        <span className="inline-flex items-center gap-2 rounded-full border border-indigo-400/25 bg-indigo-500/10 px-3 py-1 text-[11px] font-medium text-indigo-300">
          <Icon name="spark" className="h-3.5 w-3.5" />
          Grounded in live financial data
        </span>
        <h1 className="mt-5 text-3xl font-bold tracking-tight text-white sm:text-4xl">
          What do you want to analyze?
        </h1>
        <p className="mt-3 max-w-xl text-sm leading-6 text-slate-400">
          Search for a company, confirm the listing, and ask anything. Every figure comes from a financial
          tool call, and the conversation is saved to your history.
        </p>
      </div>

      <form onSubmit={start} className="mt-8 animate-fade-up">
        <div className="panel p-2">
          <div className="relative">
            <span className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-slate-500">
              <Icon name="search" className="h-4 w-4" />
            </span>
            <input
              autoFocus
              type="text"
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setSelected(null);
              }}
              placeholder="Company name or ticker, e.g. NVIDIA or RELIANCE.NS"
              aria-label="Search for a company"
              className="w-full rounded-xl border border-transparent bg-transparent py-3.5 pl-11 pr-10 text-sm text-slate-100 placeholder-slate-500 outline-none focus:border-indigo-400/50"
            />
            {searching && (
              <span className="absolute right-4 top-1/2 -translate-y-1/2 text-indigo-300">
                <Spinner />
              </span>
            )}
          </div>

          {results.length > 0 && (
            <div className="mt-1 max-h-64 space-y-1 overflow-y-auto border-t border-white/[0.06] pt-2">
              {results.map((result) => (
                <button
                  key={result.symbol}
                  type="button"
                  onClick={() => setSelected(result)}
                  className={`flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left transition ${
                    selected?.symbol === result.symbol
                      ? "bg-indigo-500/15 ring-1 ring-inset ring-indigo-400/40"
                      : "hover:bg-white/[0.04]"
                  }`}
                >
                  <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-white/10 bg-white/[0.04] text-[10px] font-bold text-indigo-300">
                    {result.symbol.slice(0, 4)}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium text-slate-200">
                      {result.name}
                      <span className="ml-2 text-xs font-normal text-slate-500">{result.symbol}</span>
                    </span>
                    <span className="block text-xs text-slate-500">{result.exchange}</span>
                  </span>
                  {selected?.symbol === result.symbol && (
                    <Icon name="check" className="h-4 w-4 shrink-0 text-indigo-300" />
                  )}
                </button>
              ))}
            </div>
          )}
        </div>

        {error && (
          <div className="mt-3">
            <ErrorBanner>{error}</ErrorBanner>
          </div>
        )}

        <button type="submit" disabled={!selected} className="btn-primary mt-4 w-full py-3">
          <Icon name="chart" className="h-4 w-4" />
          {selected ? `Start analysis · ${selected.symbol}` : "Select a listing to start"}
        </button>
      </form>

      <div className="mt-10 animate-fade-up">
        <div className="mb-3 flex items-center gap-2 text-slate-400">
          <Icon name="history" className="h-4 w-4" />
          <h2 className="text-xs font-semibold uppercase tracking-wider">Recent conversations</h2>
        </div>
        {conversations.length === 0 ? (
          <EmptyState
            icon="clock"
            title="Nothing here yet"
            hint="Once you ask a question, the conversation appears here and in the sidebar so you can return to it."
          />
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            {conversations.slice(0, 4).map((conversation) => (
              <button
                key={conversation.id}
                type="button"
                onClick={() => onOpenConversation(conversation)}
                className="panel panel-hover p-4 text-left"
              >
                <span className="flex items-center justify-between gap-2">
                  <span className="flex items-center gap-2">
                    <span className="text-sm font-semibold text-slate-200">
                      {conversation.company || conversation.ticker}
                    </span>
                    <span className="rounded-md border border-white/10 bg-white/[0.04] px-1.5 py-0.5 text-[10px] font-bold text-indigo-300">
                      {conversation.ticker}
                    </span>
                  </span>
                  <span className="text-[10px] text-slate-600">{formatTime(conversation.updated_at)}</span>
                </span>
                <span className="mt-2 block truncate text-xs leading-5 text-slate-500">
                  {conversation.preview || `${conversation.message_count} messages`}
                </span>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
