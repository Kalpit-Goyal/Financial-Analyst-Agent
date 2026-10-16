import { useState } from "react";
import { formatTime } from "../lib/format";
import TickerSearch from "./TickerSearch";
import { EmptyState, Icon } from "./ui";

export default function NewAnalysis({ onSubmit, conversations = [], onOpenConversation }) {
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState(null);

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
          <TickerSearch
            autoFocus
            query={query}
            onQueryChange={(value) => {
              setQuery(value);
              setSelected(null);
            }}
            selected={selected}
            onSelect={setSelected}
          />
        </div>

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
