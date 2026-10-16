import Markdown from "./Markdown";
import { Icon } from "./ui";

const TOOL_LABELS = {
  get_financials: "income statement",
  get_balance_sheet: "balance sheet",
  get_cash_flow: "cash flow",
  get_market_data: "market data",
  calculate: "calculations",
};

function toolLabel(name) {
  return TOOL_LABELS[name] || name;
}

function ToolChips({ tools }) {
  if (!tools?.length) return null;
  return (
    <div className="mb-3 flex flex-wrap gap-1.5">
      {tools.map((tool, index) => (
        <span
          key={`${tool}-${index}`}
          className="inline-flex items-center gap-1.5 rounded-full border border-indigo-400/25 bg-indigo-500/10 px-2.5 py-1 text-[11px] font-medium text-indigo-300"
        >
          <Icon name="chart" className="h-3 w-3" />
          {toolLabel(tool)}
        </span>
      ))}
    </div>
  );
}

export default function MessageBubble({ role, content, tools = [], error = false, streaming = false }) {
  const isUser = role === "user";

  if (isUser) {
    return (
      <div className="flex w-full justify-end">
        <div className="max-w-[85%] rounded-2xl rounded-br-md bg-gradient-to-r from-indigo-500 to-violet-500 px-4 py-3 text-sm leading-7 text-white shadow-lg shadow-indigo-950/30 sm:max-w-[75%]">
          {content}
        </div>
      </div>
    );
  }

  return (
    <div className="flex w-full items-start gap-3">
      <span className="mt-1 hidden h-8 w-8 shrink-0 items-center justify-center rounded-xl border border-white/10 bg-white/[0.04] text-indigo-300 sm:flex">
        <Icon name="spark" className="h-4 w-4" />
      </span>
      <div
        className={`min-w-0 flex-1 rounded-2xl rounded-tl-md border px-4 py-4 text-sm sm:px-5 ${
          error
            ? "border-rose-400/30 bg-rose-500/[0.07]"
            : "border-white/[0.07] bg-white/[0.025]"
        }`}
      >
        <ToolChips tools={tools} />
        {content ? (
          <Markdown>{content}</Markdown>
        ) : (
          <span className="text-slate-500">Thinking…</span>
        )}
        {streaming && content && (
          <span className="ml-0.5 inline-block h-4 w-[2px] animate-pulse rounded bg-indigo-400 align-middle" />
        )}
      </div>
    </div>
  );
}
