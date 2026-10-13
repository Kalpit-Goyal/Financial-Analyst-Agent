import { useState, useEffect } from "react";

function CompanySetup({ onSubmit }) {
  const [company, setCompany] = useState("");
  const [results, setResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [selected, setSelected] = useState(null);

  useEffect(() => {
    let cancelled = false;
    const timer = setTimeout(() => {
      async function search() {
        if (company.trim().length >= 2) {
          setSearching(true);
          try {
            const response = await fetch(`${import.meta.env.VITE_API_URL ?? "http://localhost:8000"}/resolve?q=${encodeURIComponent(company)}`);
            if (!response.ok) {
              if (!cancelled) setResults([]);
            } else {
              const data = await response.json();
              if (!cancelled) {
                setResults(data.results || []);
              }
            }
          } catch {
            if (!cancelled) setResults([]);
          } finally {
            if (!cancelled) setSearching(false);
          }
        } else {
          setResults([]);
          setSearching(false);
        }
      }
      search();
    }, 350);

    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [company]);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (selected) {
      onSubmit(selected.symbol, selected.name, selected.exchange);
    }
  };

  return (
    <div className="min-h-screen bg-white text-gray-900 flex items-center justify-center px-6">
      <div className="w-full max-w-xl">
        <div className="text-center mb-10">
          <div className="flex justify-center mb-5">
            <div className="h-14 w-14 rounded-2xl bg-blue-600 flex items-center justify-center">
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="18" y1="20" x2="18" y2="10"/>
                <line x1="12" y1="20" x2="12" y2="4"/>
                <line x1="6" y1="20" x2="6" y2="14"/>
                <polyline points="3 15 9 9 15 13 21 5"/>
              </svg>
            </div>
          </div>
          <h1 className="text-4xl font-bold tracking-tight">
            Financial Analyst
          </h1>
          <p className="mt-3 text-gray-500">
            Your AI-powered financial research assistant
          </p>
        </div>

        <form onSubmit={handleSubmit} className="bg-white border border-gray-200 rounded-2xl p-7 shadow-lg">
          <label className="block text-sm font-medium text-gray-600 mb-2">
            Company Name
          </label>

          <div className="relative">
            <input
              type="text"
              value={company}
              onChange={(e) => { setCompany(e.target.value); setSelected(null); }}
              placeholder="e.g. NVIDIA"
              className="w-full bg-white border border-gray-300 rounded-xl px-4 py-3 text-gray-900 placeholder-gray-400 outline-none focus:border-blue-500 transition pr-10"
            />
            {searching && (
              <div className="absolute right-3 top-1/2 -translate-y-1/2 flex items-center gap-1 text-gray-400">
                <span className="w-4 h-4 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
              </div>
            )}
          </div>

          {results.length > 0 && (
            <div className="mt-3 space-y-1 max-h-48 overflow-y-auto">
              {results.map((r, i) => (
                <button
                  key={i}
                  type="button"
                  onClick={() => setSelected(r)}
                  className={`w-full text-left px-3 py-2 rounded-lg text-sm border ${
                    selected?.symbol === r.symbol
                      ? "border-blue-500 bg-blue-50 text-blue-700"
                      : "border-gray-200 hover:border-gray-300 hover:bg-gray-50"
                  }`}
                >
                  <div className="font-medium">{r.name} <span className="text-gray-500 font-normal">({r.symbol})</span></div>
                  <div className="text-xs text-gray-500">{r.exchange}</div>
                </button>
              ))}
            </div>
          )}

          <button
            type="submit"
            disabled={!selected}
            className="w-full mt-6 bg-blue-600 hover:bg-blue-500 disabled:bg-gray-100 disabled:text-gray-400 disabled:cursor-not-allowed rounded-xl py-3 font-medium transition"
          >
            Start Analysis
          </button>
        </form>

        <p className="text-center text-xs text-gray-400 mt-5">
          Enter a company name to begin your analysis
        </p>
      </div>
    </div>
  );
}

export default CompanySetup;