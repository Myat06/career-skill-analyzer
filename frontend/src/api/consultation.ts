import { api, API_BASE } from "./client";

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface ConsultResponse {
  reply: string;
  status: "ok" | "unavailable";
}

export const consultationApi = {
  send: (studentId: string, messages: ChatMessage[], jobRoleId?: string) =>
    api.post<ConsultResponse>(`/students/${studentId}/consult`, {
      messages,
      job_role_id: jobRoleId ?? null,
    }),
};

export interface RoadmapStep {
  timeframe: string;
  actions: string;
}

export interface ConsultationSummary {
  job_role_title: string;
  match_percentage: number;
  executive_summary: string;
  coach_message: string;
  recommended_direction: string;
  next_step: RoadmapStep | null;
  confidence: Record<string, string>;
  resume_note: string | null;
}

export const reportsApi = {
  reportPdfUrl: (studentId: string, jobRoleId: string) =>
    `${API_BASE}/students/${studentId}/consultation-report.pdf?job_role_id=${encodeURIComponent(jobRoleId)}`,
  posterPngUrl: (studentId: string, jobRoleId: string) =>
    `${API_BASE}/students/${studentId}/consultation-poster.png?job_role_id=${encodeURIComponent(jobRoleId)}`,
  // Returns the advisory content that went into the PDF/poster. Called after a
  // download, this hits the server-side consultation cache (same inputs, same
  // fingerprint), so it costs no additional model time.
  summary: (studentId: string, jobRoleId: string) =>
    api.get<ConsultationSummary>(
      `/students/${studentId}/consultation-summary?job_role_id=${encodeURIComponent(jobRoleId)}`,
    ),
};
