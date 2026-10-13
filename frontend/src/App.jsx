import { useState } from "react";
import CompanySetup from "./components/CompanySetup";
import ChatWindow from "./components/ChatWindow";

function App() {
  const [company, setCompany] = useState("");
  const [ticker, setTicker] = useState("");
  const [started, setStarted] = useState(false);

  const handleCompanySubmit = (tickerSymbol, companyName) => {
    setCompany(companyName);
    setTicker(tickerSymbol);
    setStarted(true);
  };

  if (!started) {
    return <CompanySetup onSubmit={handleCompanySubmit} />;
  }

  return (
    <ChatWindow
      company={company}
      ticker={ticker}
    />
  );
}

export default App;