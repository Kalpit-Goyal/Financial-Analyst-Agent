import { useState } from "react";
import { useAuth } from "../lib/auth-context";
import { ErrorBanner, Field, Icon, Logo, Spinner } from "./ui";

const FEATURES = [
  {
    icon: "chart",
    title: "Answers backed by live data",
    text: "Income statement, balance sheet, cash flow and market data pulled through financial tools, not guessed by a model.",
  },
  {
    icon: "history",
    title: "Your research, saved",
    text: "Every question and answer is kept per account, per company, so you can pick a thread back up any time.",
  },
  {
    icon: "bell",
    title: "A monitor that watches for you",
    text: "Your watchlist is scanned on a schedule. Big moves get investigated, fact-checked, and turned into alerts.",
  },
];

export default function AuthScreen() {
  const { login, register } = useAuth();
  const [mode, setMode] = useState("signin");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const isSignup = mode === "signup";

  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      if (isSignup) await register(email, password, name.trim());
      else await login(email, password);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const switchMode = (next) => {
    setMode(next);
    setError("");
  };

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[1.1fr_1fr]">
      {/* Brand panel */}
      <aside className="relative hidden overflow-hidden border-r border-white/[0.06] lg:flex lg:flex-col lg:justify-between lg:p-14">
        <div
          className="pointer-events-none absolute inset-0 opacity-70"
          style={{
            background:
              "radial-gradient(700px 420px at 20% 0%, rgba(99,102,241,0.22), transparent 60%), radial-gradient(600px 380px at 90% 90%, rgba(139,92,246,0.16), transparent 60%)",
          }}
        />
        <div className="relative">
          <div className="flex items-center gap-3">
            <Logo />
            <div>
              <p className="text-sm font-semibold text-white">Financial Analyst</p>
              <p className="text-xs text-slate-400">AI research &amp; autonomous monitoring</p>
            </div>
          </div>

          <h1 className="mt-16 max-w-xl text-4xl font-bold leading-tight tracking-tight text-white">
            Research any company with data it can&apos;t make up.
          </h1>
          <p className="mt-4 max-w-lg text-[15px] leading-7 text-slate-400">
            Pick a ticker. Ask in plain English. The agent calls live Yahoo Finance tools for every figure and
            shows you which tools it used.
          </p>

          <div className="mt-12 space-y-6">
            {FEATURES.map((feature) => (
              <div key={feature.title} className="flex max-w-lg items-start gap-4">
                <span className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-white/10 bg-white/[0.04] text-indigo-300">
                  <Icon name={feature.icon} className="h-4.5 w-4.5" />
                </span>
                <div>
                  <p className="text-sm font-semibold text-slate-100">{feature.title}</p>
                  <p className="mt-1 text-sm leading-6 text-slate-400">{feature.text}</p>
                </div>
              </div>
            ))}
          </div>
        </div>

        <p className="relative text-xs text-slate-500">
          AI-generated analysis can contain errors. Not investment advice.
        </p>
      </aside>

      {/* Form panel */}
      <main className="flex min-h-screen items-center justify-center px-6 py-12">
        <div className="w-full max-w-md animate-fade-up">
          <div className="mb-8 flex items-center gap-3 lg:hidden">
            <Logo />
            <div>
              <p className="text-sm font-semibold text-white">Financial Analyst</p>
              <p className="text-xs text-slate-400">AI financial research</p>
            </div>
          </div>

          <div className="panel p-7 sm:p-8">
            <h2 className="text-xl font-semibold text-white">
              {isSignup ? "Create your account" : "Welcome back"}
            </h2>
            <p className="mt-1.5 text-sm text-slate-400">
              {isSignup
                ? "History and the monitor are saved to your account."
                : "Sign in to your research history and monitor."}
            </p>

            <div className="mt-6 grid grid-cols-2 rounded-xl border border-white/10 bg-white/[0.02] p-1 text-sm">
              {[
                ["signin", "Sign in"],
                ["signup", "Create account"],
              ].map(([value, label]) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => switchMode(value)}
                  className={`rounded-lg px-3 py-2 font-medium transition ${
                    mode === value
                      ? "bg-gradient-to-r from-indigo-500 to-violet-500 text-white shadow"
                      : "text-slate-400 hover:text-slate-200"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>

            <form onSubmit={submit} className="mt-6 space-y-4">
              {isSignup && (
                <Field
                  label="Name"
                  icon="user"
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Your name (optional)"
                  autoComplete="name"
                />
              )}
              <Field
                label="Email"
                icon="mail"
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                autoComplete="email"
              />
              <Field
                label="Password"
                icon="lock"
                type="password"
                required
                minLength={isSignup ? 8 : undefined}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder={isSignup ? "At least 8 characters" : "Your password"}
                autoComplete={isSignup ? "new-password" : "current-password"}
              />

              <ErrorBanner>{error}</ErrorBanner>

              <button type="submit" disabled={busy} className="btn-primary w-full py-3">
                {busy ? <Spinner /> : <Icon name={isSignup ? "spark" : "arrowUp"} className="h-4 w-4" />}
                {busy ? "Please wait…" : isSignup ? "Create account" : "Sign in"}
              </button>
            </form>
          </div>

          <p className="mt-5 text-center text-xs text-slate-500">
            {isSignup ? "Already have an account? " : "New here? "}
            <button
              type="button"
              onClick={() => switchMode(isSignup ? "signin" : "signup")}
              className="font-medium text-indigo-400 hover:text-indigo-300"
            >
              {isSignup ? "Sign in" : "Create an account"}
            </button>
          </p>
        </div>
      </main>
    </div>
  );
}
