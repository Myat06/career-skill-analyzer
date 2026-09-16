import { api } from "./client";
import type { ChatMessage } from "./consultation";
import type { DisplayMessage } from "../components/ChatPanel";
import type { JobRole } from "../types";

export interface ChatSessionSummary {
  id: string;
  title: string | null;
  job_role_id: string | null;
  pinned: boolean;
  updated_at: string;
}

export interface ChatSessionDetail extends ChatSessionSummary {
  display_messages: DisplayMessage[];
  chat_history: ChatMessage[];
  job_role: JobRole | null;
}

export interface ChatSessionSaveIn {
  display_messages: DisplayMessage[];
  chat_history: ChatMessage[];
  job_role_id?: string | null;
}

export const chatSessionsApi = {
  list: (studentId: string) => api.get<ChatSessionSummary[]>(`/students/${studentId}/chat-sessions`),
  get: (studentId: string, sessionId: string) =>
    api.get<ChatSessionDetail>(`/students/${studentId}/chat-sessions/${sessionId}`),
  create: (studentId: string, payload: ChatSessionSaveIn) =>
    api.post<ChatSessionDetail>(`/students/${studentId}/chat-sessions`, payload),
  update: (studentId: string, sessionId: string, payload: ChatSessionSaveIn) =>
    api.patch<ChatSessionDetail>(`/students/${studentId}/chat-sessions/${sessionId}`, payload),
  setPinned: (studentId: string, sessionId: string, pinned: boolean) =>
    api.patch<ChatSessionDetail>(`/students/${studentId}/chat-sessions/${sessionId}/pin`, { pinned }),
  remove: (studentId: string, sessionId: string) =>
    api.del<void>(`/students/${studentId}/chat-sessions/${sessionId}`),
};
