import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { studentsApi } from "./api/students";
import type { Student } from "./types";

interface StudentContextValue {
  students: Student[];
  selectedStudent: Student | null;
  selectStudent: (student: Student) => void;
  loading: boolean;
  error: string | null;
  refresh: () => void;
}

const StudentContext = createContext<StudentContextValue | null>(null);

export function StudentProvider({ children }: { children: ReactNode }) {
  const [students, setStudents] = useState<Student[]>([]);
  const [selectedStudent, setSelectedStudent] = useState<Student | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    setLoading(true);
    studentsApi
      .list()
      .then((list) => {
        setStudents(list);
        setSelectedStudent((prev) => prev ?? list[0] ?? null);
        setError(null);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load students"))
      .finally(() => setLoading(false));
  }, [tick]);

  return (
    <StudentContext.Provider
      value={{
        students,
        selectedStudent,
        selectStudent: setSelectedStudent,
        loading,
        error,
        refresh: () => setTick((t) => t + 1),
      }}
    >
      {children}
    </StudentContext.Provider>
  );
}

export function useStudentContext() {
  const ctx = useContext(StudentContext);
  if (!ctx) throw new Error("useStudentContext must be used within a StudentProvider");
  return ctx;
}
