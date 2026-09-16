import { useState } from "react";
import Modal from "./Modal";
import { studentsApi } from "../api/students";
import type { ActivityIn, ActivityOut, ActivityType } from "../types";
import { IconClose, IconSpinner } from "./icons";

const ACTIVITY_TYPES: ActivityType[] = [
  "project",
  "certification",
  "internship",
  "organization",
  "competition",
  "volunteer",
];

interface Props {
  studentId: string;
  activities: ActivityOut[];
  onClose: () => void;
  onAdded: (activity: ActivityOut) => void;
  onRemoved: (activityId: string) => void;
}

export default function AddActivityModal({ studentId, activities, onClose, onAdded, onRemoved }: Props) {
  const [type, setType] = useState<ActivityType>("project");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [issuer, setIssuer] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [evidenceUrl, setEvidenceUrl] = useState("");
  const [skillsText, setSkillsText] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [removingId, setRemovingId] = useState<string | null>(null);
  const [removeError, setRemoveError] = useState<string | null>(null);

  const handleSubmit = async () => {
    if (!title.trim() || !description.trim()) {
      setError("Title and description are required.");
      return;
    }
    setSubmitting(true);
    setError(null);
    const payload: ActivityIn = {
      type,
      title: title.trim(),
      description: description.trim(),
      issuer: issuer.trim() || undefined,
      start_date: startDate || undefined,
      end_date: endDate || undefined,
      evidence_url: evidenceUrl.trim() || undefined,
      skills_tags: skillsText
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean),
    };
    try {
      const activity = await studentsApi.addActivity(studentId, payload);
      onAdded(activity);
      setTitle("");
      setDescription("");
      setIssuer("");
      setStartDate("");
      setEndDate("");
      setEvidenceUrl("");
      setSkillsText("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add activity");
    } finally {
      setSubmitting(false);
    }
  };

  const handleRemove = async (activityId: string) => {
    setRemovingId(activityId);
    setRemoveError(null);
    try {
      await studentsApi.removeActivity(studentId, activityId);
      onRemoved(activityId);
    } catch (err) {
      setRemoveError(err instanceof Error ? err.message : "Couldn't remove that activity — try again.");
    } finally {
      setRemovingId(null);
    }
  };

  const inputClass =
    "w-full rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-sm text-slate-900 placeholder:text-slate-400 outline-none focus:border-brand-navy";
  const labelClass = "mb-1.5 block text-xs font-bold text-slate-500";

  return (
    <Modal
      title="Add a project or activity"
      subtitle="Logged activities strengthen your match and resume score."
      onClose={onClose}
      width="560px"
      footer={
        <>
          <button
            type="button"
            onClick={onClose}
            className="rounded-full border border-slate-200 px-4 py-2.5 text-sm font-semibold text-slate-500 hover:bg-slate-50"
          >
            Close
          </button>
          <button
            type="button"
            disabled={submitting}
            onClick={() => void handleSubmit()}
            className="rounded-full bg-brand-navy px-5 py-2.5 text-sm font-semibold text-white disabled:opacity-50"
          >
            {submitting ? "Saving…" : "Save Activity"}
          </button>
        </>
      }
    >
      {activities.length > 0 && (
        <div className="mb-5 flex flex-col gap-2">
          <span className={labelClass}>Already logged ({activities.length})</span>
          {removeError && <p className="text-sm text-brand-red">{removeError}</p>}
          {activities.map((a) => (
            <div
              key={a.id}
              className="flex items-center gap-3 rounded-2xl border border-slate-200 bg-slate-50 px-3.5 py-2.5"
            >
              <span className="rounded-full bg-brand-teal-soft px-2.5 py-1 text-[11px] font-bold capitalize text-brand-teal">
                {a.type}
              </span>
              <div className="min-w-0 flex-1">
                <div className="truncate text-sm font-bold text-slate-900">{a.title}</div>
                <div className="truncate text-xs text-slate-400">{a.description}</div>
              </div>
              <button
                type="button"
                onClick={() => void handleRemove(a.id)}
                disabled={removingId === a.id}
                className="flex h-6 w-6 flex-none items-center justify-center rounded-full text-slate-300 hover:bg-red-50 hover:text-brand-red disabled:opacity-50"
                aria-label={`Remove ${a.title}`}
                title="Remove"
              >
                {removingId === a.id ? <IconSpinner size={13} /> : <IconClose size={13} />}
              </button>
            </div>
          ))}
        </div>
      )}

      <div className="flex flex-col gap-4.5 border-t border-slate-100 pt-4.5">
        <span className={labelClass}>Add new</span>
        <div>
          <span className={labelClass}>Type</span>
          <div className="flex flex-wrap gap-2">
            {ACTIVITY_TYPES.map((t) => (
              <button
                type="button"
                key={t}
                onClick={() => setType(t)}
                className={`rounded-full border-[1.5px] px-3.5 py-1.5 text-xs font-bold capitalize ${
                  type === t
                    ? "border-brand-navy bg-brand-navy-soft text-brand-navy-strong"
                    : "border-slate-200 text-slate-500"
                }`}
              >
                {t}
              </button>
            ))}
          </div>
        </div>

        <div>
          <span className={labelClass}>Title</span>
          <input className={inputClass} value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Warehouse Layout Optimization" />
        </div>

        <div>
          <span className={labelClass}>Description</span>
          <textarea
            className={inputClass}
            rows={3}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="What did you do, and what was the outcome?"
          />
        </div>

        <div className="grid grid-cols-1 gap-3.5 sm:grid-cols-2">
          <div>
            <span className={labelClass}>Issuer / Organizer</span>
            <input className={inputClass} value={issuer} onChange={(e) => setIssuer(e.target.value)} placeholder="e.g. Logistics Lab" />
          </div>
          <div>
            <span className={labelClass}>Evidence link (optional)</span>
            <input className={inputClass} value={evidenceUrl} onChange={(e) => setEvidenceUrl(e.target.value)} placeholder="https://…" />
          </div>
        </div>

        <div className="grid grid-cols-1 gap-3.5 sm:grid-cols-2">
          <div>
            <span className={labelClass}>Start date</span>
            <input type="date" className={inputClass} value={startDate} onChange={(e) => setStartDate(e.target.value)} />
          </div>
          <div>
            <span className={labelClass}>End date</span>
            <input type="date" className={inputClass} value={endDate} onChange={(e) => setEndDate(e.target.value)} />
          </div>
        </div>

        <div>
          <span className={labelClass}>Skills (comma-separated)</span>
          <input className={inputClass} value={skillsText} onChange={(e) => setSkillsText(e.target.value)} placeholder="Inventory Layout, Excel" />
        </div>

        {error && <p className="text-sm text-brand-red">{error}</p>}
      </div>
    </Modal>
  );
}
