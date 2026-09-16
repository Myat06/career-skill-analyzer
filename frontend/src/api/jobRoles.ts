import { api } from "./client";
import type { JobRole, JobRoleResolveResult } from "../types";

export const jobRolesApi = {
  list: () => api.get<JobRole[]>("/job-roles"),
  resolve: (query: string) => api.get<JobRoleResolveResult>(`/job-roles/resolve?query=${encodeURIComponent(query)}`),
};
