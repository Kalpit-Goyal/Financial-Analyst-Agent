import { useState } from "react";
import CompanySetup from "./components/CompanySetup";
import ChatWindow from "./components/ChatWindow";
import MonitorPanel from "./components/MonitorPanel";

function App() {
  const [company, setCompany] = useState("");
  const [ticker, setTicker] = useState("");
  const [started, setStarted] = useState(false);
  const [view, setView] = useState("analyst");

  const handleCompanySubmit = (tickerSymbol, companyName) => {
    setCompany(companyName);
    setTicker(tickerSymbol);
    setStarted(true);
  };

  const openMonitor = () => setView("monitor");

  return (
    <>
      {/* Kept mounted while the monitor is open so an ongoing chat is not lost. */}
      <div className={view === "monitor" ? "hidden" : undefined}>
        {started ? (
          <ChatWindow company={company} ticker={ticker} onOpenMonitor={openMonitor} />
        ) : (
          <CompanySetup onSubmit={handleCompanySubmit} onOpenMonitor={openMonitor} />
        )}
      </div>
      {view === "monitor" && <MonitorPanel onBack={() => setView("analyst")} />}
    </>
  );
}

export default App;
