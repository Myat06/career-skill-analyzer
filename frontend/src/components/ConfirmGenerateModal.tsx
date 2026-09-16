import Modal from "./Modal";
import type { JobRole } from "../types";

interface Props {
  mode: "report" | "poster";
  jobRole: JobRole;
  onClose: () => void;
  onConfirm: () => void;
}

export default function ConfirmGenerateModal({ mode, jobRole, onClose, onConfirm }: Props) {
  const label = mode === "report" ? "Consultation Report" : "Expo Poster";

  return (
    <Modal
      title={`Generate ${label}?`}
      subtitle={`For your target role: ${jobRole.role_title}`}
      width="440px"
      onClose={onClose}
      footer={
        <>
          <button
            type="button"
            onClick={onClose}
            className="rounded-xl border border-slate-200 px-4 py-2.5 text-sm font-semibold text-slate-600 hover:bg-slate-50"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onConfirm}
            className="rounded-xl bg-brand-red px-4 py-2.5 text-sm font-semibold text-white hover:opacity-90"
          >
            Generate
          </button>
        </>
      }
    >
      <p className="text-sm text-slate-600">
        This takes a minute or two to build. Compass Coach will post progress in chat, then download the file
        automatically when it's ready — no need to stay on this page.
      </p>
    </Modal>
  );
}
