import { useState } from "react";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { StudentProvider } from "./StudentContext";
import { ChatSessionProvider, useChatSessionContext } from "./ChatSessionContext";
import StudentSwitcher from "./components/StudentSwitcher";
import { IconMenu, IconPanel, IconPin, IconPlus, IconTrash } from "./components/icons";
import Consultation from "./pages/Consultation";
import IngestionAdmin from "./pages/IngestionAdmin";

function formatRelativeTime(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime();
  const minutes = Math.round(diffMs / 60000);
  if (minutes < 1) return "Just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  if (days < 7) return `${days}d ago`;
  return new Date(iso).toLocaleDateString();
}

function ChatHistoryList() {
  const { sessions, activeSessionId, setActiveSessionId, deleteSession, setSessionPinned } = useChatSessionContext();

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-2.5">
      <button
        type="button"
        onClick={() => setActiveSessionId(null)}
        className="flex flex-none items-center gap-2 rounded-xl border border-dashed border-slate-300 px-3 py-2.5 text-left text-sm font-semibold text-slate-600 hover:border-slate-400 hover:bg-slate-50"
      >
        <IconPlus size={14} />
        New Chat
      </button>

      {sessions.length > 0 && (
        <div className="flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto">
          <div className="px-2 text-[11px] font-bold uppercase tracking-wide text-slate-400">History</div>
          {sessions.map((s) => {
            const isActive = s.id === activeSessionId;
            return (
              <div
                key={s.id}
                className={`group flex w-full items-center gap-0.5 rounded-xl px-2.5 py-2 ${
                  isActive ? "bg-brand-navy-soft" : "hover:bg-slate-50"
                }`}
              >
                <button
                  type="button"
                  onClick={() => setActiveSessionId(s.id)}
                  className="flex min-w-0 flex-1 flex-col items-start gap-0.5 text-left"
                >
                  <span className="flex w-full items-center gap-1">
                    {s.pinned && <IconPin size={10} className="flex-none text-brand-navy" />}
                    <span className="block truncate text-sm font-semibold text-slate-900">
                      {s.title ?? "New chat"}
                    </span>
                  </span>
                  <span className="text-xs text-slate-400">{formatRelativeTime(s.updated_at)}</span>
                </button>
                <button
                  type="button"
                  onClick={() => void setSessionPinned(s.id, !s.pinned)}
                  className={`flex h-6 w-6 flex-none items-center justify-center rounded-full text-slate-300 hover:bg-slate-200 hover:text-slate-600 ${
                    s.pinned ? "" : "opacity-0 group-hover:opacity-100"
                  }`}
                  aria-label={s.pinned ? "Unpin chat" : "Pin chat"}
                >
                  <IconPin size={12} />
                </button>
                <button
                  type="button"
                  onClick={() => {
                    if (window.confirm(`Delete "${s.title ?? "this chat"}"? This can't be undone.`)) {
                      void deleteSession(s.id);
                    }
                  }}
                  className="flex h-6 w-6 flex-none items-center justify-center rounded-full text-slate-300 opacity-0 hover:bg-red-100 hover:text-brand-red group-hover:opacity-100"
                  aria-label="Delete chat"
                >
                  <IconTrash size={12} />
                </button>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function Sidebar({ onClose }: { onClose: () => void }) {
  return (
    <aside className="flex w-full flex-none flex-col gap-4 border-b border-slate-200 bg-white px-4 py-4 lg:sticky lg:top-0 lg:h-screen lg:w-64 lg:gap-5 lg:overflow-y-auto lg:border-b-0 lg:border-r lg:px-4.5 lg:py-7">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2.5 px-2">
          <span className="flex h-8.5 w-8.5 flex-none items-center justify-center overflow-hidden rounded-lg border border-slate-200 bg-white">
            <img src="/pu-logo.jpg" alt="President University" className="h-full w-full object-contain" />
          </span>
          <span className="text-lg font-bold text-brand-navy">PresConsult AI</span>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="flex h-7 w-7 flex-none items-center justify-center rounded-full border border-slate-200 text-slate-400 hover:bg-slate-50"
          aria-label="Collapse sidebar"
        >
          <IconPanel size={13} />
        </button>
      </div>
      <ChatHistoryList />
      <StudentSwitcher />
    </aside>
  );
}

function Shell() {
  const [showSidebar, setShowSidebar] = useState(true);

  return (
    <div className="flex min-h-screen flex-col lg:flex-row">
      {showSidebar && <Sidebar onClose={() => setShowSidebar(false)} />}
      <main className="relative flex flex-1 flex-col gap-5.5 px-4 pb-8 pt-6 sm:px-6 lg:px-11 lg:pt-9">
        {!showSidebar && (
          <button
            type="button"
            onClick={() => setShowSidebar(true)}
            className="fixed left-4 top-4 z-10 flex h-9 w-9 items-center justify-center rounded-full border border-slate-200 bg-white text-slate-500 shadow-sm hover:bg-slate-50"
            aria-label="Show sidebar"
          >
            <IconMenu size={16} />
          </button>
        )}
        <Routes>
          <Route path="/" element={<Consultation />} />
          <Route path="/ingestion" element={<IngestionAdmin />} />
        </Routes>
      </main>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <StudentProvider>
        <ChatSessionProvider>
          <Shell />
        </ChatSessionProvider>
      </StudentProvider>
    </BrowserRouter>
  );
}
