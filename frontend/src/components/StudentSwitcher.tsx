import { useEffect, useRef, useState } from "react";
import { useStudentContext } from "../StudentContext";
import { IconCheck, IconChevronRight } from "./icons";
import type { Student } from "../types";

function initials(fullName: string) {
  const parts = fullName.trim().split(/\s+/);
  const first = parts[0]?.[0] ?? "";
  const last = parts.length > 1 ? parts[parts.length - 1][0] : "";
  return (first + last).toUpperCase();
}

export default function StudentSwitcher() {
  const { students, selectedStudent, selectStudent, loading, error } = useStudentContext();
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    };
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  if (loading) return <span className="text-sm text-slate-400">Loading…</span>;
  if (error) return <span className="text-sm text-brand-red">{error}</span>;

  const pick = (student: Student) => {
    selectStudent(student);
    setOpen(false);
  };

  return (
    <div ref={rootRef} className="relative lg:mt-auto">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-2.5 rounded-full border border-slate-200 bg-white px-2 py-1.5 hover:bg-slate-50 lg:w-full lg:justify-start lg:rounded-2xl lg:border-0 lg:bg-slate-50 lg:px-3 lg:py-2.5 lg:hover:bg-slate-100"
      >
        <span className="flex h-8 w-8 flex-none items-center justify-center rounded-full bg-brand-navy text-xs font-bold text-white">
          {selectedStudent ? initials(selectedStudent.full_name) : "—"}
        </span>
        <span className="hidden min-w-0 flex-1 text-left lg:block">
          <span className="block truncate text-sm font-semibold text-slate-900">
            {selectedStudent?.full_name ?? "Select student"}
          </span>
          <span className="block truncate text-xs text-slate-500">{selectedStudent?.program ?? "President University"}</span>
        </span>
        <IconChevronRight size={13} className="hidden flex-none -rotate-90 text-slate-300 lg:block" />
      </button>

      {open && (
        <div className="absolute right-0 top-full z-20 mt-2 w-72 max-h-80 overflow-y-auto rounded-2xl border border-slate-200 bg-white p-1.5 shadow-2xl lg:right-auto lg:bottom-full lg:left-0 lg:top-auto lg:mt-0 lg:mb-2 lg:w-full">
          {students.map((student) => {
            const isSelected = student.id === selectedStudent?.id;
            return (
              <button
                type="button"
                key={student.id}
                onClick={() => pick(student)}
                className={`flex w-full items-center gap-2.5 rounded-xl px-2.5 py-2 text-left ${
                  isSelected ? "bg-brand-navy-soft" : "hover:bg-slate-50"
                }`}
              >
                <span className="flex h-7 w-7 flex-none items-center justify-center rounded-full bg-brand-navy text-[10px] font-bold text-white">
                  {initials(student.full_name)}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-semibold text-slate-900">{student.full_name}</span>
                  <span className="block truncate text-xs text-slate-500">
                    {student.program} · {student.student_no}
                  </span>
                </span>
                {isSelected && <IconCheck size={14} className="flex-none text-brand-navy" />}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
