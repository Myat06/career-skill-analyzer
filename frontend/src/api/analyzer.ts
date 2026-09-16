import { api } from "./client";
import type { SkillGapResponse, SkillGapSummary } from "../types";

export interface SkillGapRequest {
  job_role_id?: string;
  job_role_query?: string;
  include_uploaded_resume?: boolean;
}

export const analyzerApi = {
  runSkillGap: (studentId: string, payload: SkillGapRequest) =>
    api.post<SkillGapResponse>(`/analyzer/skill-gap?student_id=${studentId}`, payload),
  getSkillGap: (analysisId: string) => api.get<SkillGapResponse>(`/analyzer/skill-gap/${analysisId}`),
  history: (studentId: string) => api.get<SkillGapSummary[]>(`/students/${studentId}/skill-gap/history`),
};
