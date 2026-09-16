import type { JobRole, SkillGapResponse } from "../types";
import { IconActivity, IconCheck, IconChevronRight, IconPoster, IconReport, IconSpinner, IconUpload } from "./icons";

interface ResumeInfo {
  id: string;
  fileName: string;
  overallScore: number | null;
}

interface Props {
  skillGap: SkillGapResponse | null;
  currentJobRole: JobRole | null;
  analyzingRole: boolean;
  resumeInfo: ResumeInfo | null;
  uploadingResume: boolean;
  activitiesCount: number;
  generatingMode: "report" | "poster" | null;
  onUploadResume: () => void;
  onAddActivity: () => void;
  onChooseRole: () => void;
  onGenerateReport: () => void;
  onGeneratePoster: () => void;
}

function ActionButton({
  icon,
  iconBg,
  iconColor,
  label,
  description,
  onClick,
  loading = false,
  disabled = false,
}: {
  icon: React.ReactNode;
  iconBg: string;
  iconColor: string;
  label: string;
  description: string;
  onClick: () => void;
  loading?: boolean;
  disabled?: boolean;
}) {
  // `loading` used to be purely decorative (a spinner icon) with the button still
  // fully clickable underneath -- nothing stopped a double-click or a stray extra
  // click from firing a second multi-minute generation on top of the first. This
  // is now an actual `disabled` button while an action for it is in flight.
  const isDisabled = disabled || loading;
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={isDisabled}
      className={`flex items-center gap-3 rounded-2xl border border-slate-200 bg-white px-3.5 py-3 text-left ${
        isDisabled ? "cursor-not-allowed opacity-60" : "hover:border-slate-300"
      }`}
    >
      <span className={`flex h-8.5 w-8.5 flex-none items-center justify-center rounded-xl ${iconBg} ${iconColor}`}>
        {icon}
      </span>
      <span className="flex-1">
        <span className="block text-sm font-bold text-slate-900">{label}</span>
        <span className="block text-xs text-slate-400">{description}</span>
      </span>
      {loading ? (
        <IconSpinner className="flex-none text-brand-teal" />
      ) : (
        <IconChevronRight className="flex-none text-slate-300" />
      )}
    </button>
  );
}

export default function ContextPanel({
  skillGap,
  currentJobRole,
  analyzingRole,
  resumeInfo,
  uploadingResume,
  activitiesCount,
  generatingMode,
  onUploadResume,
  onAddActivity,
  onChooseRole,
  onGenerateReport,
  onGeneratePoster,
}: Props) {
  const topGap = skillGap?.missing_units[0] ?? skillGap?.partial_units[0];

  return (
    <div className="animate-panel-in flex w-full flex-col gap-4.5 lg:w-85 lg:flex-none">
      <div className="px-1">
        <span className="text-xs font-bold uppercase tracking-wide text-slate-400">Profile &amp; Tools</span>
      </div>

      <div className="rounded-3xl border border-slate-200 border-t-[3px] border-t-brand-blue bg-white p-6 shadow-sm">
        <div className="text-xs font-bold uppercase tracking-wide text-brand-blue">Your context</div>

        <div className="mt-3.5 flex flex-col gap-2">
          <div className="text-[11px] font-bold uppercase tracking-wide text-slate-400">Referenced in this chat</div>
          <div className="flex items-center gap-2">
            {uploadingResume ? (
              <>
                <IconSpinner className="text-brand-teal" />
                <span className="text-sm text-slate-700">Uploading &amp; analyzing resume…</span>
              </>
            ) : (
              <>
                <IconCheck className={resumeInfo ? "text-emerald-500" : "text-slate-300"} />
                <span className="text-sm text-slate-700">{resumeInfo ? resumeInfo.fileName : "No resume uploaded yet"}</span>
              </>
            )}
          </div>
          <div className="flex items-center gap-2">
            <IconCheck className={activitiesCount > 0 ? "text-emerald-500" : "text-slate-300"} />
            <span className="text-sm text-slate-700">{activitiesCount} activities logged</span>
          </div>
        </div>

        {analyzingRole ? (
          <div className="mt-3.5 flex items-center gap-2.5 border-t border-slate-100 pt-3.5">
            <IconSpinner className="text-brand-blue" />
            <span className="text-sm font-semibold text-slate-500">
              Analyzing your match against this role — this can take a minute…
            </span>
          </div>
        ) : currentJobRole ? (
          <div className="mt-3.5 flex items-center justify-between border-t border-slate-100 pt-3.5">
            <span className="text-sm text-slate-500">
              Match — {currentJobRole.role_title}
              <button type="button" onClick={onChooseRole} className="ml-2 text-xs font-bold text-brand-blue hover:underline">
                Change
              </button>
            </span>
            <strong className="text-lg font-bold text-slate-900">
              {skillGap ? `${skillGap.match_percentage.toFixed(0)}%` : "—"}
            </strong>
          </div>
        ) : (
          <button
            type="button"
            onClick={onChooseRole}
            className="mt-3.5 flex w-full items-center justify-between rounded-xl border border-dashed border-slate-300 px-3.5 py-2.5 text-left"
          >
            <span className="text-sm font-semibold text-slate-500">Choose your target role</span>
            <IconChevronRight className="text-slate-300" />
          </button>
        )}
        {skillGap && (
          <div className="mt-3.5 flex gap-1.5 border-t border-slate-100 pt-3.5">
            <span className="rounded-full bg-emerald-100 px-3 py-1 text-xs font-bold text-emerald-700">
              {skillGap.matched_units.length} Matched
            </span>
            <span className="rounded-full bg-amber-100 px-3 py-1 text-xs font-bold text-amber-700">
              {skillGap.partial_units.length} Partial
            </span>
            <span className="rounded-full bg-red-100 px-3 py-1 text-xs font-bold text-brand-red">
              {skillGap.missing_units.length} Missing
            </span>
          </div>
        )}

        {topGap && (
          <div className="mt-3.5">
            <div className="mb-1 text-xs text-slate-400">Top gap</div>
            <span className="rounded-full bg-red-100 px-3 py-1 text-xs font-bold text-brand-red">
              {topGap.unit_title}
            </span>
          </div>
        )}
      </div>

      <div className="rounded-3xl border border-slate-200 border-t-[3px] border-t-brand-teal bg-white p-6 shadow-sm">
        <div className="mb-3.5 text-xs font-bold uppercase tracking-wide text-brand-teal">Build your profile</div>
        <div className="flex flex-col gap-2.5">
          <ActionButton
            icon={<IconUpload size={17} />}
            iconBg="bg-brand-teal-soft"
            iconColor="text-brand-teal"
            label="Upload Resume"
            description={uploadingResume ? "Uploading & analyzing…" : "Compass Coach will review it in chat"}
            onClick={onUploadResume}
            loading={uploadingResume}
          />
          <ActionButton
            icon={<IconActivity size={17} />}
            iconBg="bg-brand-teal-soft"
            iconColor="text-brand-teal"
            label="Add Project / Activity"
            description="Log it manually for better matches"
            onClick={onAddActivity}
          />
        </div>
      </div>

      <div className="rounded-3xl border border-slate-200 border-t-[3px] border-t-brand-red bg-white p-6 shadow-sm">
        <div className="mb-3.5 text-xs font-bold uppercase tracking-wide text-brand-red">Generate</div>
        <div className="flex flex-col gap-2.5">
          <ActionButton
            icon={<IconReport size={17} />}
            iconBg="bg-brand-red-soft"
            iconColor="text-brand-red"
            label="Consultation Report"
            description={generatingMode === "report" ? "Generating…" : "Summary PDF for a role you pick"}
            onClick={onGenerateReport}
            loading={generatingMode === "report"}
            disabled={generatingMode === "poster"}
          />
          <ActionButton
            icon={<IconPoster size={17} />}
            iconBg="bg-brand-red-soft"
            iconColor="text-brand-red"
            label="Expo Poster"
            description={generatingMode === "poster" ? "Generating…" : "Shareable graphic for a role you pick"}
            onClick={onGeneratePoster}
            loading={generatingMode === "poster"}
            disabled={generatingMode === "report"}
          />
        </div>
      </div>
    </div>
  );
}
