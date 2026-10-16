import { useCallback, useEffect, useState } from "react";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth-context";
import { formatTime } from "../lib/format";
import TickerSearch from "./TickerSearch";
import { Badge, EmptyState, ErrorBanner, Icon, Spinner } from "./ui";

const TICKER_PATTERN = /^[A-Za-z0-9.\-^=]{1,15}$/;

async function fetchAll() {
  const [watchlist, runs, alerts, stats] = await Promise.all([
    api("/watchlist"),
    api("/monitor/runs?limit=6"),
    api("/monitor/alerts?limit=20"),
    api("/monitor/stats"),
  ]);
  return { watchlist: watchlist.items, runs: runs.items, alerts: alerts.items, stats };
}

function describeRun(run) {
  if (!run) return "The scheduled scan also runs on its own; this button runs it for your watchlist right now.";
  const when = formatTime(run.started_at);
  if (run.status === "running") return `Running since ${when}.`;
  if (run.status === "failed") return `Failed on ${when}${run.error ? `: ${run.error}` : "."}`;
  const summary = run.summary || {};
  const alerts = summary.alerts?.length ?? 0;
  const errors = summary.errors?.length ?? 0;
  return `Last finished ${when}: ${alerts} alert${alerts === 1 ? "" : "s"}, ${summary.quiet ?? 0} quiet, ${errors} error${errors === 1 ? "" : "s"}.`;
}

const STANCE_TONE = { bullish: "emerald", bearish: "rose", neutral: "slate" };

function StatCard({ label, value, icon }) {
  return (
    <div className="panel flex items-center gap-3 p-4">
      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-white/10 bg-white/[0.04] text-indigo-300">
        <Icon name={icon} className="h-4 w-4" />
      </span>
      <span>
        <span className="block text-[11px] uppercase tracking-wider text-slate-500">{label}</span>
        <span className="block text-lg font-semibold text-white">{value}</span>
      </span>
    </div>
  );
}

function AlertCard({ alert, horizon }) {
  const scored = alert.outcome_at && alert.return_pct !== null;
  return (
    <article className="panel p-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-semibold text-white">{alert.ticker}</span>
        {alert.verified ? (
          <Badge tone={STANCE_TONE[alert.stance] ?? "slate"}>
            {alert.stance}, {alert.confidence} confidence
          </Badge>
        ) : (
          <Badge tone="amber">Signals only</Badge>
        )}
        {alert.verified && <Badge tone="indigo">Fact-checked</Badge>}
        {!alert.sent && <Badge tone="slate">Not delivered</Badge>}
        <span className="ml-auto text-[11px] text-slate-600">{formatTime(alert.created_at)}</span>
      </div>
      <p className="mt-3 text-sm font-medium leading-6 text-slate-200">{alert.headline}</p>
      {alert.verified && <p className="mt-1 text-sm leading-6 text-slate-400">{alert.summary}</p>}
      {alert.triggers?.length > 0 && (
        <p className="mt-2 text-[11px] text-slate-500">Triggered by: {alert.triggers.join(" · ")}</p>
      )}
      <p className="mt-2 text-[11px] text-slate-500">
        {scored
          ? `After ${horizon} days: ${alert.return_pct > 0 ? "+" : ""}${alert.return_pct}%${
              alert.hit === null ? " (not scored)" : alert.hit ? " · call was right" : " · call was wrong"
            }`
          : `Outcome is scored ${horizon} days after the alert.`}
      </p>
    </article>
  );
}

export default function MonitorPanel({ onOpenAnalysis }) {
  const { logout } = useAuth();
  const [watchlist, setWatchlist] = useState([]);
  const [runs, setRuns] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  const handleError = useCallback(
    (err) => {
      if (err.status === 401) logout();
      else setError(err.message);
    },
    [logout]
  );

  const refresh = useCallback(async () => {
    try {
      const data = await fetchAll();
      setWatchlist(data.watchlist);
      setRuns(data.runs);
      setAlerts(data.alerts);
      setStats(data.stats);
      setError("");
    } catch (err) {
      handleError(err);
    } finally {
      setLoading(false);
    }
  }, [handleError]);

  useEffect(() => {
    let cancelled = false;
    fetchAll()
      .then((data) => {
        if (cancelled) return;
        setWatchlist(data.watchlist);
        setRuns(data.runs);
        setAlerts(data.alerts);
        setStats(data.stats);
        setError("");
      })
      .catch((err) => {
        if (!cancelled) handleError(err);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [handleError]);

  const running = runs[0]?.status === "running";
  useEffect(() => {
    if (!running) return undefined;
    const timer = setInterval(refresh, 4000);
    return () => clearInterval(timer);
  }, [running, refresh]);

  const act = async (fn) => {
    setBusy(true);
    try {
      await fn();
      await refresh();
    } catch (err) {
      handleError(err);
    } finally {
      setBusy(false);
    }
  };

  const addTicker = (event) => {
    event.preventDefault();
    const symbol = (selected?.symbol ?? query.trim()).toUpperCase();
    if (!selected && !TICKER_PATTERN.test(symbol)) {
      setError("Search for a company first, or enter a ticker symbol such as NVDA or RELIANCE.NS.");
      return;
    }
    act(async () => {
      await api("/watchlist", {
        method: "POST",
        body: { ticker: symbol, note: note.trim() || null },
      });
      setQuery("");
      setSelected(null);
      setNote("");
    });
  };

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-5xl px-5 py-8 sm:px-8">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-2xl font-bold tracking-tight text-white">Autonomous monitor</h1>
              {running && (
                <Badge tone="violet">
                  <Spinner className="h-3 w-3" /> scanning
                </Badge>
              )}
            </div>
            <p className="mt-1.5 max-w-2xl text-sm leading-6 text-slate-400">
              Your watchlist is checked on a schedule and on demand. Big price moves and upcoming earnings are
              investigated with the analyst agent, fact-checked, and turned into alerts below.
            </p>
          </div>
          <button
            type="button"
            onClick={() => act(() => api("/monitor/run", { method: "POST" }))}
            disabled={busy || running || watchlist.length === 0}
            className="btn-primary"
          >
            {running ? <Spinner /> : <Icon name="refresh" className="h-4 w-4" />}
            {running ? "Scan in progress…" : "Run scan now"}
          </button>
        </div>

        {error && (
          <div className="mt-5">
            <ErrorBanner>{error}</ErrorBanner>
          </div>
        )}

        <div className="mt-7 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard label="Alerts sent" value={loading ? "–" : (stats?.alerts ?? 0)} icon="bell" />
          <StatCard label="Scored" value={loading ? "–" : (stats?.scored ?? 0)} icon="check" />
          <StatCard
            label="Hit rate"
            value={loading ? "–" : stats?.hit_rate == null ? "Not yet" : `${Math.round(stats.hit_rate * 100)}%`}
            icon="trend"
          />
          <StatCard
            label="Avg signed return"
            value={
              loading
                ? "–"
                : stats?.avg_signed_return_pct == null
                  ? "Not yet"
                  : `${stats.avg_signed_return_pct > 0 ? "+" : ""}${stats.avg_signed_return_pct}%`
            }
            icon="chart"
          />
        </div>
        <p className="mt-2 text-[11px] leading-5 text-slate-600">
          Each alert is scored {stats?.horizon_days ?? 7} days later against the actual price move. Neutral and
          signals-only alerts are not scored.
        </p>

        <div className="mt-9 grid gap-6 lg:grid-cols-2">
          <section>
            <div className="mb-3 flex items-center gap-2">
              <Icon name="activity" className="h-4 w-4 text-indigo-300" />
              <h2 className="text-sm font-semibold text-white">Watchlist</h2>
              <span className="text-xs text-slate-500">({watchlist.length}/25)</span>
            </div>

            <form onSubmit={addTicker} className="panel mb-3 space-y-2 p-3">
              <TickerSearch
                query={query}
                onQueryChange={(value) => {
                  setQuery(value);
                  setSelected(null);
                }}
                selected={selected}
                onSelect={setSelected}
                placeholder="Company name or ticker, e.g. NVDA"
                ariaLabel="Search for a company to add"
                inputClassName="input-dark pl-10"
              />
              <input
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder="Why you watch it (optional)"
                aria-label="Note"
                maxLength={500}
                className="input-dark"
              />
              <button type="submit" disabled={busy || !query.trim()} className="btn-ghost w-full">
                <Icon name="plus" className="h-4 w-4" />
                {selected ? `Add ${selected.symbol} to watchlist` : "Add to watchlist"}
              </button>
            </form>

            {watchlist.length === 0 ? (
              <EmptyState
                icon="activity"
                title="Your watchlist is empty"
                hint="Add tickers you care about. The scheduled run checks them after market closes, and the monitor investigates anything unusual."
              />
            ) : (
              <ul className="panel divide-y divide-white/[0.05]">
                {watchlist.map((item) => (
                  <li key={item.ticker} className="flex items-center gap-3 px-4 py-3">
                    <span className="w-24 shrink-0 truncate text-sm font-semibold text-slate-200">
                      {item.ticker}
                    </span>
                    <span className="min-w-0 flex-1 truncate text-xs text-slate-500">{item.note}</span>
                    <button
                      type="button"
                      aria-label={`Remove ${item.ticker}`}
                      disabled={busy}
                      onClick={() =>
                        act(() =>
                          api(`/watchlist/${encodeURIComponent(item.ticker)}`, { method: "DELETE" })
                        )
                      }
                      className="rounded-lg p-1.5 text-slate-500 transition hover:bg-white/[0.06] hover:text-rose-300 disabled:opacity-50"
                    >
                      <Icon name="trash" className="h-4 w-4" />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section>
            <div className="mb-3 flex items-center gap-2">
              <Icon name="bell" className="h-4 w-4 text-indigo-300" />
              <h2 className="text-sm font-semibold text-white">Recent alerts</h2>
            </div>
            {alerts.length === 0 ? (
              <EmptyState
                icon="shield"
                title="No alerts yet"
                hint="The agent only alerts when a ticker has a large move or earnings coming up and the analysis passes its fact-check. Silence means nothing deserved an interruption."
              />
            ) : (
              <div className="space-y-3">
                {alerts.map((alert) => (
                  <AlertCard key={alert.id} alert={alert} horizon={stats?.horizon_days ?? 7} />
                ))}
              </div>
            )}
          </section>
        </div>

        <section className="mt-9">
          <div className="mb-3 flex items-center gap-2">
            <Icon name="clock" className="h-4 w-4 text-indigo-300" />
            <h2 className="text-sm font-semibold text-white">Recent runs</h2>
          </div>
          <div className="panel divide-y divide-white/[0.05]">
            {(runs.length === 0 ? [null] : runs).map((run, index) => (
              <div key={run?.id ?? index} className="flex items-center gap-3 px-4 py-3">
                {run?.status === "running" ? (
                  <Spinner className="h-3.5 w-3.5 text-violet-300" />
                ) : (
                  <span
                    className={`h-2 w-2 shrink-0 rounded-full ${
                      run?.status === "failed" ? "bg-rose-400" : "bg-emerald-400"
                    }`}
                  />
                )}
                <p className="text-sm text-slate-300">{describeRun(run)}</p>
              </div>
            ))}
          </div>
          <button type="button" onClick={onOpenAnalysis} className="btn-ghost mt-4">
            <Icon name="plus" className="h-4 w-4" />
            Start a new analysis
          </button>
        </section>
      </div>
    </div>
  );
}
