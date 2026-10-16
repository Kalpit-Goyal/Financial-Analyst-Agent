import { useCallback, useEffect, useState } from "react";
import AuthProvider from "./components/AuthProvider";
import AuthScreen from "./components/AuthScreen";
import ChatPanel from "./components/ChatPanel";
import MonitorPanel from "./components/MonitorPanel";
import NewAnalysis from "./components/NewAnalysis";
import Sidebar from "./components/Sidebar";
import { Icon, Logo, Spinner } from "./components/ui";
import { api } from "./lib/api";
import { useAuth } from "./lib/auth-context";

function Splash() {
  return (
    <div className="flex h-screen items-center justify-center">
      <div className="flex items-center gap-3 text-slate-400">
        <Logo />
        <span className="flex items-center gap-2 text-sm">
          <Spinner /> Loading your workspace…
        </span>
      </div>
    </div>
  );
}

function Workspace() {
  const { user, logout } = useAuth();
  const [view, setView] = useState("new"); // new | chat | monitor
  const [active, setActive] = useState(null); // { id, company, ticker }
  const [conversations, setConversations] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [menuOpen, setMenuOpen] = useState(false);

  const refreshHistory = useCallback(async () => {
    try {
      const data = await api("/conversations");
      setConversations(data.items);
    } catch (err) {
      if (err.status === 401) logout();
    } finally {
      setHistoryLoading(false);
    }
  }, [logout]);

  useEffect(() => {
    let cancelled = false;
    api("/conversations")
      .then((data) => {
        if (!cancelled) setConversations(data.items);
      })
      .catch((err) => {
        if (!cancelled && err.status === 401) logout();
      })
      .finally(() => {
        if (!cancelled) setHistoryLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [logout]);

  const navigate = (key) => {
    setMenuOpen(false);
    if (key === "new") {
      setActive(null);
      setView("new");
    } else {
      setView(key);
    }
  };

  const startAnalysis = (company, ticker) => {
    setActive({ id: null, company, ticker });
    setView("chat");
  };

  const openConversation = (conversation) => {
    setMenuOpen(false);
    setActive({
      id: conversation.id,
      company: conversation.company || conversation.ticker,
      ticker: conversation.ticker,
    });
    setView("chat");
  };

  const deleteConversation = async (conversation) => {
    try {
      await api(`/conversations/${conversation.id}`, { method: "DELETE" });
      setConversations((prev) => prev.filter((c) => c.id !== conversation.id));
      if (active?.id === conversation.id) {
        setActive(null);
        setView("new");
      }
    } catch (err) {
      if (err.status === 401) logout();
    }
  };

  const sidebarProps = {
    user,
    view,
    onNavigate: navigate,
    conversations,
    historyLoading,
    activeConversationId: active?.id ?? null,
    onOpenConversation: openConversation,
    onDeleteConversation: deleteConversation,
    onSignOut: logout,
  };

  return (
    <div className="h-screen overflow-hidden text-slate-200">
      <Sidebar {...sidebarProps} className="fixed inset-y-0 left-0 z-30 hidden lg:flex" />

      {menuOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div
            className="absolute inset-0 bg-black/60 backdrop-blur-sm"
            onClick={() => setMenuOpen(false)}
            aria-hidden="true"
          />
          <Sidebar
            {...sidebarProps}
            onClose={() => setMenuOpen(false)}
            className="absolute inset-y-0 left-0 z-50 flex animate-fade-in"
          />
        </div>
      )}

      <div className="flex h-full flex-col lg:pl-72">
        <header className="flex items-center gap-3 border-b border-white/[0.06] bg-ink-900/70 px-4 py-3 backdrop-blur lg:hidden">
          <button
            type="button"
            onClick={() => setMenuOpen(true)}
            aria-label="Open menu"
            className="rounded-lg border border-white/10 bg-white/[0.03] p-2 text-slate-300"
          >
            <Icon name="menu" className="h-4 w-4" />
          </button>
          <Logo />
          <p className="text-sm font-semibold text-white">Financial Analyst</p>
          <button
            type="button"
            onClick={() => navigate("monitor")}
            aria-label="Open the autonomous monitor"
            className="ml-auto rounded-lg border border-white/10 bg-white/[0.03] p-2 text-indigo-300"
          >
            <Icon name="activity" className="h-4 w-4" />
          </button>
        </header>

        <main className="min-h-0 flex-1">
          {/* Kept mounted while the monitor is open so an ongoing answer is not lost. */}
          <div className={view === "monitor" ? "hidden" : "h-full"}>
            {view === "new" && (
              <NewAnalysis
                onSubmit={startAnalysis}
                conversations={conversations}
                onOpenConversation={openConversation}
              />
            )}
            {view === "chat" && active && (
              <ChatPanel
                company={active.company}
                ticker={active.ticker}
                conversationId={active.id}
                onConversationCreated={(id) => {
                  setActive((prev) => (prev ? { ...prev, id } : prev));
                  refreshHistory();
                }}
                onOpenMonitor={() => setView("monitor")}
              />
            )}
          </div>
          {view === "monitor" && <MonitorPanel onOpenAnalysis={() => navigate("new")} />}
        </main>
      </div>
    </div>
  );
}

function Gate() {
  const { user, loading } = useAuth();
  if (loading) return <Splash />;
  if (!user) return <AuthScreen />;
  return <Workspace />;
}

export default function App() {
  return (
    <AuthProvider>
      <Gate />
    </AuthProvider>
  );
}
