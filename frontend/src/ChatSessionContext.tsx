import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { useStudentContext } from "./StudentContext";
import { chatSessionsApi, type ChatSessionSummary } from "./api/chatSessions";

interface ChatSessionContextValue {
  sessions: ChatSessionSummary[];
  // null = drafting a fresh/unsaved chat ("New Chat"), otherwise the id of
  // the session currently shown in Consultation.tsx.
  activeSessionId: string | null;
  setActiveSessionId: (id: string | null) => void;
  refreshSessions: () => void;
  deleteSession: (id: string) => Promise<void>;
  setSessionPinned: (id: string, pinned: boolean) => Promise<void>;
}

const ChatSessionContext = createContext<ChatSessionContextValue | null>(null);

export function ChatSessionProvider({ children }: { children: ReactNode }) {
  const { selectedStudent } = useStudentContext();
  const [sessions, setSessions] = useState<ChatSessionSummary[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  // Guards the async list() response below against a student switch that
  // happens before it resolves -- otherwise a slow fetch for the OLD
  // student could land after the switch and overwrite the new student's
  // already-correct session list.
  const currentStudentIdRef = useRef<string | null>(null);

  const studentId = selectedStudent?.id ?? null;

  // Reset synchronously DURING render (React's documented "adjusting state
  // when a prop changes" pattern), not in a useEffect, when the student
  // changes. This is a provider ABOVE Consultation.tsx in the tree, and
  // React runs child effects before parent effects within the same commit
  // -- an effect-based reset here would fire one commit too late, letting
  // Consultation's own session-load effect (which reacts to activeSessionId)
  // briefly see the OLD student's activeSessionId paired with the NEW
  // student's id, and try (and fail) to fetch a session that belongs to
  // someone else. Resetting here instead means activeSessionId is already
  // null in the very same render Consultation sees the new selectedStudent.
  const [lastStudentId, setLastStudentId] = useState<string | null>(studentId);
  if (studentId !== lastStudentId) {
    setLastStudentId(studentId);
    setActiveSessionId(null);
    setSessions([]);
    currentStudentIdRef.current = studentId;
  }

  useEffect(() => {
    if (!studentId) return;
    chatSessionsApi
      .list(studentId)
      .then((list) => {
        if (currentStudentIdRef.current === studentId) setSessions(list);
      })
      .catch(() => {});
  }, [studentId, tick]);

  const refreshSessions = () => setTick((t) => t + 1);

  const deleteSession = async (id: string) => {
    if (!studentId) return;
    await chatSessionsApi.remove(studentId, id);
    // Deleting the session currently open in Consultation.tsx must not leave
    // it pointing at a now-nonexistent id -- fall back to a fresh draft,
    // same as clicking New Chat.
    setActiveSessionId((current) => (current === id ? null : current));
    refreshSessions();
  };

  const setSessionPinned = async (id: string, pinned: boolean) => {
    if (!studentId) return;
    await chatSessionsApi.setPinned(studentId, id, pinned);
    refreshSessions();
  };

  return (
    <ChatSessionContext.Provider
      value={{
        sessions,
        activeSessionId,
        setActiveSessionId,
        refreshSessions,
        deleteSession,
        setSessionPinned,
      }}
    >
      {children}
    </ChatSessionContext.Provider>
  );
}

export function useChatSessionContext() {
  const ctx = useContext(ChatSessionContext);
  if (!ctx) throw new Error("useChatSessionContext must be used within a ChatSessionProvider");
  return ctx;
}
