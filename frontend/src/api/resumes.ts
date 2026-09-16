import { api } from "./client";
import type { ResumeOut, ResumeScoreOut } from "../types";

export const resumesApi = {
  upload: (studentId: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return api.postForm<ResumeOut>(`/students/${studentId}/resume/upload`, form);
  },
  latest: (studentId: string) => api.get<ResumeOut>(`/students/${studentId}/resume/latest`),
  remove: (studentId: string, resumeId: string) => api.del<void>(`/students/${studentId}/resume/${resumeId}`),
  score: (resumeId: string, jobRoleId?: string) => {
    const query = jobRoleId ? `?job_role_id=${encodeURIComponent(jobRoleId)}` : "";
    return api.get<ResumeScoreOut>(`/resumes/${resumeId}/score${query}`);
  },
};
