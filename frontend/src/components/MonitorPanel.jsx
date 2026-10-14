import { useCallback, useEffect, useState } from "react";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
const TOKEN_KEY = "monitor_token";
const TICKER_PATTERN = /^[A-Za-z0-9.\-^=]{1,15}$/;

class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

async function request(token, path, options = {}) {
  let response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
    });
  } catch {
    throw new ApiError(0, "Could not reach the server. Check that the backend is running.");
  }
  if (!response.ok) {
    let detail = "";
    try {
      const body = await response.json();
      detail = typeof body.detail === "string" ? body.detail : "";
    } catch {
      /* body was not JSON */
    }
    if (response.status === 401) throw new ApiError(401, "That token was not accepted.");
    if (response.status === 429) throw new ApiError(429, "Too many requests. Wait a minute and try again.");
    throw new ApiError(response.status, detail || `Request failed (${response.status}).`);
  }
  return response.json();
}

async function fetchAll(token) {
  const [w, r, a, st] = await Promise.all([
    request(token, "/watchlist"),
    request(token, "/monitor/runs?limit=5"),
    request(token, "/monitor/alerts?limit=20"),
    request(token, "/monitor/stats"),
  ]);
  return { watchlist: w.items, runs: r.items, alerts: a.items, stats: st };
}

function formatTime(iso) {
  return iso ? new Date(iso).toLocaleString([], { dateStyle: "medium", timeStyle: "short" }) : "";
}

function describeRun(run) {
  if (!run) return "No runs yet.";
  const when = formatTime(run.started_at);
  if (run.status === "running") return `Running since ${when}.`;
  if (run.status === "failed") return `Failed on ${when}${run.error ? `: ${run.error}` : "."}`;
  const s = run.summary || {};
  const alerts = s.alerts?.length ?? 0;
  const errors = s.errors?.length ?? 0;
  return `Finished ${when}: ${alerts} alert${alerts === 1 ? "" : "s"}, ${s.quiet ?? 0} quiet, ${errors} error${errors === 1 ? "" : "s"}.`;
}

const STANCE_STYLES = {
  bullish: "bg-green-50 text-green-700 border-green-200",
  bearish: "bg-red-50 text-red-700 border-red-200",
  neutral: "bg-gray-50 text-gray-600 border-gray-200",
};

function Badge({ className, children }) {
  return (
    <span className={`text-xs font-medium px-2 py-0.5 rounded-full border ${className}`}>
      {children}
    </span>
  );
}

function Section({ title, hint, children }) {
  return (
    <section className="mb-10">
      <h2 className="text-lg font-semibold">{title}</h2>
      {hint && <p className="text-sm text-gray-500 mt-1 mb-4">{hint}</p>}
      {!hint && <div className="mb-4" />}
      {children}
    </section>
  );
}

function AlertCard({ alert, horizon }) {
  const scored = alert.outcome_at && alert.return_pct !== null;
  return (
    <div className="border border-gray-200 rounded-xl p-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-semibold">{alert.ticker}</span>
        {alert.verified ? (
          <Badge className={STANCE_STYLES[alert.stance] || STANCE_STYLES.neutral}>
            {alert.stance}, {alert.confidence} confidence
          </Badge>
        ) : (
          <Badge className="bg-amber-50 text-amber-700 border-amber-200">Signals only</Badge>
        )}
        {alert.verified && <Badge className="bg-blue-50 text-blue-700 border-blue-200">Checked against data</Badge>}
        {!alert.sent && <Badge className="bg-gray-50 text-gray-500 border-gray-200">Not delivered</Badge>}
        <span className="text-xs text-gray-400 ml-auto">{formatTime(alert.created_at)}</span>
      </div>
      <p className="text-sm font-medium mt-3">{alert.headline}</p>
      {alert.verified && <p className="text-sm text-gray-600 mt-1">{alert.summary}</p>}
      {alert.triggers.length > 0 && (
        <p className="text-xs text-gray-500 mt-2">Triggered by: {alert.triggers.join(", ")}</p>
      )}
      <p className="text-xs text-gray-500 mt-1">
        {scored
          ? `After ${horizon} days: ${alert.return_pct > 0 ? "+" : ""}${alert.return_pct}%${
              alert.hit === null ? " (not scored)" : alert.hit ? " (call was right)" : " (call was wrong)"
            }`
          : `Outcome is scored ${horizon} days after the alert.`}
      </p>
    </div>
  );
}

function TokenGate({ onUnlock, onBack }) {
  const [value, setValue] = useState("");
  const [error, setError] = useState("");
  const [checking, setChecking] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setChecking(true);
    setError("");
    try {
      await request(value.trim(), "/watchlist");
      onUnlock(value.trim());
    } catch (err) {
      setError(
        err.status === 503
          ? "This server has no OWNER_TOKEN set, so the monitor is switched off."
          : err.message
      );
    } finally {
      setChecking(false);
    }
  };

  return (
    <div className="min-h-screen bg-white text-gray-900 flex items-center justify-center px-6">
      <form onSubmit={submit} className="w-full max-w-md bg-white border border-gray-200 rounded-2xl p-7 shadow-lg">
        <h1 className="text-2xl font-semibold">Autonomous monitor</h1>
        <p className="text-sm text-gray-500 mt-2">
          Enter your owner token to manage the watchlist and see alerts. It is saved in this browser only.
        </p>
        <label htmlFor="owner-token" className="block text-sm font-medium text-gray-600 mt-6 mb-2">
          Owner token
        </label>
        <input
          id="owner-token"
          type="password"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          autoComplete="off"
          className="w-full bg-white border border-gray-300 rounded-xl px-4 py-3 outline-none focus:border-blue-500 transition"
        />
        {error && <p role="alert" className="text-sm text-red-600 mt-3">{error}</p>}
        <button
          type="submit"
          disabled={!value.trim() || checking}
          className="w-full mt-6 bg-blue-600 hover:bg-blue-500 text-white disabled:bg-gray-100 disabled:text-gray-400 disabled:cursor-not-allowed rounded-xl py-3 font-medium transition"
        >
          {checking ? "Checking..." : "Unlock"}
        </button>
        <button type="button" onClick={onBack} className="w-full mt-3 text-sm text-gray-500 hover:text-gray-700">
          Back to the analyst
        </button>
      </form>
    </div>
  );
}

function MonitorPanel({ onBack }) {
  const [token, setToken] = useState(() => {
    try {
      return localStorage.getItem(TOKEN_KEY) || "";
    } catch {
      return "";
    }
  });
  const [watchlist, setWatchlist] = useState([]);
  const [runs, setRuns] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [stats, setStats] = useState(null);
  const [error, setError] = useState("");
  const [ticker, setTicker] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  const signOut = useCallback(() => {
    try {
      localStorage.removeItem(TOKEN_KEY);
    } catch {
      /* storage unavailable */
    }
    setToken("");
  }, []);

  const unlock = (value) => {
    try {
      localStorage.setItem(TOKEN_KEY, value);
    } catch {
      /* storage unavailable: the token still works for this session */
    }
    setToken(value);
  };

  const applyData = useCallback((data) => {
    setWatchlist(data.watchlist);
    setRuns(data.runs);
    setAlerts(data.alerts);
    setStats(data.stats);
    setError("");
  }, []);

  const handleError = useCallback(
    (err) => {
      if (err.status === 401) signOut();
      else setError(err.message);
    },
    [signOut]
  );

  const refresh = useCallback(async () => {
    try {
      applyData(await fetchAll(token));
    } catch (err) {
      handleError(err);
    }
  }, [token, applyData, handleError]);

  useEffect(() => {
    if (!token) return undefined;
    let cancelled = false;
    (async () => {
      try {
        const data = await fetchAll(token);
        if (!cancelled) applyData(data);
      } catch (err) {
        if (!cancelled) handleError(err);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token, applyData, handleError]);

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

  const addTicker = (e) => {
    e.preventDefault();
    const symbol = ticker.trim().toUpperCase();
    if (!TICKER_PATTERN.test(symbol)) {
      setError("Enter a ticker symbol such as NVDA or RELIANCE.NS.");
      return;
    }
    act(async () => {
      await request(token, "/watchlist", {
        method: "POST",
        body: JSON.stringify({ ticker: symbol, note: note.trim() || null }),
      });
      setTicker("");
      setNote("");
    });
  };

  if (!token) return <TokenGate onUnlock={unlock} onBack={onBack} />;

  return (
    <div className="min-h-screen bg-white text-gray-900">
      <header className="h-16 border-b border-gray-200 flex items-center px-6 gap-4">
        <div>
          <h1 className="font-semibold">Autonomous monitor</h1>
          <p className="text-xs text-gray-500">Checks your watchlist, investigates unusual moves, sends checked alerts</p>
        </div>
        <div className="ml-auto flex items-center gap-4 text-sm">
          <button onClick={onBack} className="text-blue-600 hover:text-blue-500">Back to the analyst</button>
          <button onClick={signOut} className="text-gray-500 hover:text-gray-700">Sign out</button>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-6 py-10">
        {error && (
          <p role="alert" className="mb-6 text-sm text-red-700 bg-red-50 border border-red-200 rounded-xl px-4 py-3">
            {error}
          </p>
        )}

        <Section
          title="Track record"
          hint={`Each alert is scored ${stats?.horizon_days ?? 7} days later against the actual price. Neutral and signals-only alerts are not scored.`}
        >
          <dl className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {[
              ["Alerts sent", stats?.alerts ?? 0],
              ["Scored", stats?.scored ?? 0],
              ["Hit rate", stats?.hit_rate == null ? "Not yet" : `${Math.round(stats.hit_rate * 100)}%`],
              [
                "Average return",
                stats?.avg_signed_return_pct == null ? "Not yet" : `${stats.avg_signed_return_pct > 0 ? "+" : ""}${stats.avg_signed_return_pct}%`,
              ],
            ].map(([label, value]) => (
              <div key={label} className="border border-gray-200 rounded-xl p-4">
                <dt className="text-xs text-gray-500">{label}</dt>
                <dd className="text-xl font-semibold mt-1">{value}</dd>
              </div>
            ))}
          </dl>
        </Section>

        <Section title="Run a scan" hint={describeRun(runs[0])}>
          <button
            onClick={() => act(() => request(token, "/monitor/run", { method: "POST" }))}
            disabled={busy || running || watchlist.length === 0}
            className="bg-blue-600 hover:bg-blue-500 text-white disabled:bg-gray-100 disabled:text-gray-400 disabled:cursor-not-allowed rounded-xl px-5 py-2.5 font-medium transition"
          >
            {running ? "Scan in progress..." : "Run scan now"}
          </button>
          {watchlist.length === 0 && (
            <p className="text-sm text-gray-500 mt-3">Add at least one ticker to the watchlist first.</p>
          )}
        </Section>

        <Section title="Watchlist" hint="The scheduled run checks every ticker here, after the Indian and US market closes.">
          <form onSubmit={addTicker} className="flex flex-col sm:flex-row gap-2 mb-4">
            <input
              value={ticker}
              onChange={(e) => setTicker(e.target.value)}
              placeholder="Ticker, e.g. NVDA"
              aria-label="Ticker"
              className="sm:w-44 border border-gray-300 rounded-xl px-4 py-2.5 outline-none focus:border-blue-500 transition"
            />
            <input
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="Why you are watching it (optional)"
              aria-label="Note"
              maxLength={500}
              className="flex-1 border border-gray-300 rounded-xl px-4 py-2.5 outline-none focus:border-blue-500 transition"
            />
            <button
              type="submit"
              disabled={busy || !ticker.trim()}
              className="border border-gray-300 hover:border-gray-400 disabled:text-gray-400 disabled:cursor-not-allowed rounded-xl px-5 py-2.5 font-medium transition"
            >
              Add ticker
            </button>
          </form>
          {watchlist.length === 0 ? (
            <p className="text-sm text-gray-500">No tickers yet. Add one above.</p>
          ) : (
            <ul className="divide-y divide-gray-200 border border-gray-200 rounded-xl">
              {watchlist.map((item) => (
                <li key={item.ticker} className="flex items-center gap-3 px-4 py-3">
                  <span className="font-medium w-28 shrink-0">{item.ticker}</span>
                  <span className="text-sm text-gray-500 flex-1 min-w-0 truncate">{item.note}</span>
                  <button
                    onClick={() => act(() => request(token, `/watchlist/${encodeURIComponent(item.ticker)}`, { method: "DELETE" }))}
                    disabled={busy}
                    aria-label={`Remove ${item.ticker}`}
                    className="text-sm text-gray-500 hover:text-red-600 disabled:opacity-50"
                  >
                    Remove
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Section>

        <Section title="Recent alerts">
          {alerts.length === 0 ? (
            <p className="text-sm text-gray-500">
              No alerts yet. The agent only alerts when a ticker has a large move or earnings coming up and the analysis passes its fact-check.
            </p>
          ) : (
            <div className="space-y-3">
              {alerts.map((alert) => (
                <AlertCard key={alert.id} alert={alert} horizon={stats?.horizon_days ?? 7} />
              ))}
            </div>
          )}
        </Section>
      </main>
    </div>
  );
}

export default MonitorPanel;
