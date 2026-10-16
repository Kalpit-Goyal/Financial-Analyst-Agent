import { useTickerSearch } from "../lib/use-ticker-search";
import { Icon, Spinner } from "./ui";

const DEFAULT_INPUT =
  "w-full rounded-xl border border-transparent bg-transparent py-3.5 pl-10 pr-10 text-sm text-slate-100 placeholder-slate-500 outline-none focus:border-indigo-400/50";

/**
 * Company/ticker search box with live suggestions from /resolve.
 * Controlled: the parent owns `query` and `selected`, and clears `selected`
 * whenever the query changes.
 */
export default function TickerSearch({
  query,
  onQueryChange,
  selected,
  onSelect,
  placeholder = "Company name or ticker, e.g. NVIDIA or RELIANCE.NS",
  ariaLabel = "Search for a company",
  autoFocus = false,
  inputClassName = DEFAULT_INPUT,
}) {
  const { results, searching, error } = useTickerSearch(query);

  return (
    <>
      <div className="relative">
        <span className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-500">
          <Icon name="search" className="h-4 w-4" />
        </span>
        <input
          type="text"
          value={query}
          onChange={(e) => onQueryChange(e.target.value)}
          placeholder={placeholder}
          aria-label={ariaLabel}
          autoFocus={autoFocus}
          className={inputClassName}
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
              onClick={() => onSelect(result)}
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

      {error && (
        <p className="flex items-center gap-1.5 px-1 pt-2 text-xs text-rose-300">
          <Icon name="alert" className="h-3.5 w-3.5 shrink-0" />
          {error}
        </p>
      )}
    </>
  );
}
