import { useState } from "react";

function CompanySetup({ onSubmit }) {
  const [company, setCompany] = useState("");

  const handleSubmit = (e) => {
    e.preventDefault();

    if (!company.trim()) {
      return;
    }

    onSubmit(company.trim());
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

        <form
          onSubmit={handleSubmit}
          className="bg-white border border-gray-200 rounded-2xl p-7 shadow-lg"
        >

          <label className="block text-sm font-medium text-gray-600 mb-2">
            Company Name
          </label>

          <input
            type="text"
            value={company}
            onChange={(e) => setCompany(e.target.value)}
            placeholder="e.g. NVIDIA"
            className="w-full bg-white border border-gray-300 rounded-xl px-4 py-3 text-gray-900 placeholder-gray-400 outline-none focus:border-blue-500 transition"
          />

          <button
            type="submit"
            disabled={!company.trim()}
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
