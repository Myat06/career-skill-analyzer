import { useEffect, useMemo, useState } from "react";
import Modal from "./Modal";
import { jobRolesApi } from "../api/jobRoles";
import type { JobRole } from "../types";
import { IconCheck, IconSearch } from "./icons";

interface Props {
  currentJobRole: JobRole | null;
  currentMatchPercentage: number | null;
  onClose: () => void;
  onConfirm: (role: JobRole) => void;
}

export default function RoleSelectModal({ currentJobRole, currentMatchPercentage, onClose, onConfirm }: Props) {
  const [roles, setRoles] = useState<JobRole[]>([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<JobRole | null>(currentJobRole);
  const [resolving, setResolving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    jobRolesApi
      .list()
      .then(setRoles)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load roles"))
      .finally(() => setLoading(false));
  }, []);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return roles;
    return roles.filter(
      (r) => r.role_title.toLowerCase().includes(q) || (r.sector ?? "").toLowerCase().includes(q)
    );
  }, [roles, query]);

  const handleResolveCustom = async () => {
    if (!query.trim()) return;
    setResolving(true);
    setError(null);
    try {
      const result = await jobRolesApi.resolve(query.trim());
      if (result.matched_job_role) {
        setSelected(result.matched_job_role);
        if (result.low_confidence) {
          setError(`Closest match: "${result.matched_job_role.role_title}" (low confidence) — pick it or refine your search.`);
        }
      } else {
        setError("Couldn't match that to a known role. Try a different phrasing.");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Lookup failed");
    } finally {
      setResolving(false);
    }
  };

  return (
    <Modal
      title="Choose your target role"
      subtitle="This shapes the report or poster we generate for you."
      onClose={onClose}
      footer={
        <>
          <button
            type="button"
            onClick={onClose}
            className="rounded-full border border-slate-200 px-4 py-2.5 text-sm font-semibold text-slate-500 hover:bg-slate-50"
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={!selected}
            onClick={() => selected && onConfirm(selected)}
            className="rounded-full bg-brand-navy px-5 py-2.5 text-sm font-semibold text-white disabled:opacity-40"
          >
            Continue
          </button>
        </>
      }
    >
      <div className="mb-4 flex items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-3.5 py-2.5">
        <IconSearch className="text-slate-400" />
        <input
          className="flex-1 bg-transparent text-sm text-slate-700 outline-none placeholder:text-slate-400"
          placeholder="Search job roles…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </div>

      {loading && <p className="text-sm text-slate-400">Loading roles…</p>}
      {error && <p className="mb-3 text-sm text-brand-red">{error}</p>}

      <div className="flex flex-col gap-2">
        {filtered.map((role) => {
          const isSelected = selected?.id === role.id;
          const showMatch = currentJobRole?.id === role.id && currentMatchPercentage !== null;
          return (
            <button
              type="button"
              key={role.id}
              onClick={() => setSelected(role)}
              className={`flex items-center gap-3.5 rounded-2xl border-[1.5px] px-4 py-3 text-left transition-colors ${
                isSelected ? "border-brand-navy bg-brand-navy-soft" : "border-slate-200 hover:border-slate-300"
              }`}
            >
              <div className="flex-1">
                <div className="text-sm font-bold text-slate-900">{role.role_title}</div>
                {role.sector && <div className="text-xs text-slate-400">{role.sector}</div>}
              </div>
              {showMatch && (
                <span className="rounded-full bg-emerald-100 px-3 py-1 text-xs font-bold text-emerald-700">
                  {currentMatchPercentage!.toFixed(0)}% match
                </span>
              )}
              {isSelected && (
                <span className="flex h-5 w-5 flex-none items-center justify-center rounded-full bg-brand-navy text-white">
                  <IconCheck size={12} />
                </span>
              )}
            </button>
          );
        })}

        {!loading && filtered.length === 0 && (
          <div className="flex items-center gap-3 rounded-2xl border-[1.5px] border-dashed border-slate-200 px-4 py-3">
            <div className="flex-1">
              <div className="text-sm font-semibold text-slate-500">No preset role matches "{query}"</div>
              <div className="text-xs text-slate-400">We'll match it against SKKNI competency units instead.</div>
            </div>
            <button
              type="button"
              disabled={resolving}
              onClick={handleResolveCustom}
              className="flex-none rounded-full bg-brand-navy px-3.5 py-1.5 text-xs font-bold text-white disabled:opacity-50"
            >
              {resolving ? "Matching…" : "Use this role"}
            </button>
          </div>
        )}
      </div>
    </Modal>
  );
}
