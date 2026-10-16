import { useState } from "react";
import { initials, formatTime } from "../lib/format";
import { Badge, Icon, Logo, Spinner } from "./ui";

const NAV = [
  { key: "new", label: "New analysis", icon: "plus" },
  { key: "monitor", label: "Autonomous monitor", icon: "activity" },
];

function ConversationRow({ conversation, active, onOpen, onDelete }) {
  const [confirming, setConfirming] = useState(false);

  return (
    <div
      className={`group relative flex cursor-pointer items-start gap-3 rounded-xl px-3 py-2.5 transition ${
        active ? "bg-indigo-500/10 ring-1 ring-inset ring-indigo-400/30" : "hover:bg-white/[0.04]"
      }`}
      onClick={() => onOpen(conversation)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter") onOpen(conversation);
      }}
    >
      <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border border-white/10 bg-white/[0.04] text-[10px] font-bold text-indigo-300">
        {conversation.ticker.slice(0, 4)}
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm font-medium text-slate-200">
          {conversation.company || conversation.ticker}
        </span>
        <span className="mt-0.5 block truncate text-xs text-slate-500">
          {conversation.preview || `${conversation.message_count} messages`}
        </span>
      </span>
      <span className="flex shrink-0 flex-col items-end gap-1">
        <span className="text-[10px] text-slate-600">{formatTime(conversation.updated_at)}</span>
        {confirming ? (
          <span className="flex items-center gap-1">
            <button
              type="button"
              aria-label={`Delete ${conversation.ticker} conversation`}
              className="rounded-md bg-rose-500/20 px-1.5 py-0.5 text-[10px] font-semibold text-rose-300 hover:bg-rose-500/30"
              onClick={(e) => {
                e.stopPropagation();
                onDelete(conversation);
                setConfirming(false);
              }}
            >
              Delete
            </button>
            <button
              type="button"
              aria-label="Cancel delete"
              className="rounded-md px-1 py-0.5 text-[10px] text-slate-400 hover:text-slate-200"
              onClick={(e) => {
                e.stopPropagation();
                setConfirming(false);
              }}
            >
              Keep
            </button>
          </span>
        ) : (
          <button
            type="button"
            aria-label={`Remove ${conversation.ticker} conversation`}
            className="hidden rounded-md p-1 text-slate-500 transition hover:bg-white/[0.06] hover:text-rose-300 group-hover:block"
            onClick={(e) => {
              e.stopPropagation();
              setConfirming(true);
            }}
          >
            <Icon name="trash" className="h-3.5 w-3.5" />
          </button>
        )}
      </span>
    </div>
  );
}

export default function Sidebar({
  user,
  view,
  onNavigate,
  conversations,
  historyLoading,
  activeConversationId,
  onOpenConversation,
  onDeleteConversation,
  onSignOut,
  onClose,
  className = "",
}) {
  return (
    <aside
      className={`flex h-full w-72 flex-col border-r border-white/[0.06] bg-ink-900/70 backdrop-blur-xl ${className}`}
    >
      <div className="flex items-center gap-3 px-5 pb-5 pt-6">
        <Logo />
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold text-white">Financial Analyst</p>
          <p className="truncate text-xs text-slate-500">Research &amp; monitor</p>
        </div>
        {onClose && (
          <button
            type="button"
            onClick={onClose}
            aria-label="Close menu"
            className="rounded-lg p-1.5 text-slate-400 hover:bg-white/[0.05] hover:text-white lg:hidden"
          >
            <Icon name="x" className="h-4 w-4" />
          </button>
        )}
      </div>

      <nav className="space-y-1 px-3">
        {NAV.map((item) => (
          <button
            key={item.key}
            type="button"
            onClick={() => onNavigate(item.key)}
            className={`flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition ${
              view === item.key
                ? "bg-gradient-to-r from-indigo-500/20 to-violet-500/10 text-white ring-1 ring-inset ring-indigo-400/30"
                : "text-slate-400 hover:bg-white/[0.04] hover:text-slate-200"
            }`}
          >
            <Icon name={item.icon} className="h-4 w-4" />
            {item.label}
          </button>
        ))}
      </nav>

      <div className="mt-7 flex min-h-0 flex-1 flex-col px-3">
        <div className="flex items-center justify-between px-3 pb-2">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">History</p>
          {historyLoading && <Spinner className="h-3 w-3 text-slate-500" />}
        </div>
        <div className="min-h-0 flex-1 space-y-1 overflow-y-auto pb-3">
          {conversations.length === 0 && !historyLoading ? (
            <p className="px-3 py-4 text-xs leading-5 text-slate-500">
              No conversations yet. Your first question starts a history entry.
            </p>
          ) : (
            conversations.map((conversation) => (
              <ConversationRow
                key={conversation.id}
                conversation={conversation}
                active={conversation.id === activeConversationId}
                onOpen={onOpenConversation}
                onDelete={onDeleteConversation}
              />
            ))
          )}
        </div>
      </div>

      <div className="border-t border-white/[0.06] p-3">
        <div className="flex items-center gap-3 rounded-xl px-2 py-2">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-indigo-500 to-violet-600 text-xs font-bold text-white">
            {initials(user)}
          </span>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-sm font-medium text-slate-200">{user?.name || "Analyst"}</span>
            <span className="block truncate text-xs text-slate-500">{user?.email}</span>
          </span>
          <button
            type="button"
            onClick={onSignOut}
            aria-label="Sign out"
            title="Sign out"
            className="rounded-lg p-2 text-slate-400 transition hover:bg-white/[0.05] hover:text-rose-300"
          >
            <Icon name="logout" className="h-4 w-4" />
          </button>
        </div>
        <div className="mt-1 px-2 pb-1">
          <Badge tone="slate">AI analysis · not investment advice</Badge>
        </div>
      </div>
    </aside>
  );
}
