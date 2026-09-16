import { api } from "./client";
import type { ActivityIn, ActivityOut, Student, StudentProfile } from "../types";

export const studentsApi = {
  list: () => api.get<Student[]>("/students"),
  profile: (studentId: string) => api.get<StudentProfile>(`/students/${studentId}/profile`),
  addActivity: (studentId: string, payload: ActivityIn) =>
    api.post<ActivityOut>(`/students/${studentId}/projects`, payload),
  removeActivity: (studentId: string, activityId: string) =>
    api.del<void>(`/students/${studentId}/projects/${activityId}`),
};
