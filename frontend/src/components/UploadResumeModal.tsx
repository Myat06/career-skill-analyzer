import { useRef, useState } from "react";
import Modal from "./Modal";
import { IconClose, IconReport, IconSpinner, IconUpload } from "./icons";

interface CurrentResume {
  id: string;
  fileName: string;
}

interface Props {
  currentResume: CurrentResume | null;
  onClose: () => void;
  onFileSelected: (file: File) => void;
  onRemoveResume: (resumeId: string) => Promise<void>;
}

export default function UploadResumeModal({ currentResume, onClose, onFileSelected, onRemoveResume }: Props) {
  const [dragOver, setDragOver] = useState(false);
  const [removing, setRemoving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleRemove = async () => {
    if (!currentResume) return;
    setRemoving(true);
    setError(null);
    try {
      await onRemoveResume(currentResume.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't remove that resume — try again.");
    } finally {
      setRemoving(false);
    }
  };

  return (
    <Modal
      title="Upload your resume"
      subtitle="Compass Coach will review it against your target role, right here in chat."
      onClose={onClose}
      width="480px"
      footer={
        <button
          type="button"
          onClick={onClose}
          className="rounded-full border border-slate-200 px-4 py-2.5 text-sm font-semibold text-slate-500 hover:bg-slate-50"
        >
          Cancel
        </button>
      }
    >
      {currentResume && (
        <div className="mb-4 flex items-center gap-3 rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3">
          <span className="flex h-9 w-9 flex-none items-center justify-center rounded-xl bg-brand-navy-soft text-brand-navy-strong">
            <IconReport size={16} />
          </span>
          <div className="min-w-0 flex-1">
            <div className="truncate text-sm font-bold text-slate-900">{currentResume.fileName}</div>
            <div className="text-xs text-slate-400">Currently on file</div>
          </div>
          <button
            type="button"
            onClick={() => void handleRemove()}
            disabled={removing}
            className="flex flex-none items-center gap-1.5 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-bold text-brand-red disabled:opacity-50"
          >
            {removing ? <IconSpinner size={12} /> : <IconClose size={11} />}
            {removing ? "Removing…" : "Remove"}
          </button>
        </div>
      )}

      {error && <p className="mb-3 text-sm text-brand-red">{error}</p>}

      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          const file = e.dataTransfer.files?.[0];
          if (file) onFileSelected(file);
        }}
        className={`flex flex-col items-center gap-3.5 rounded-2xl border-[1.5px] border-dashed px-6 py-9 text-center transition-colors ${
          dragOver ? "border-brand-navy bg-brand-navy-soft" : "border-slate-200 bg-slate-50"
        }`}
      >
        <span className="flex h-13 w-13 items-center justify-center rounded-2xl bg-brand-navy-soft text-brand-navy-strong">
          <IconUpload size={24} />
        </span>
        <div>
          <div className="text-sm font-bold text-slate-900">
            {currentResume ? "Drag and drop a replacement here" : "Drag and drop your resume here"}
          </div>
          <div className="mt-0.5 text-xs text-slate-400">PDF, DOCX, JPG, or PNG, up to 10MB</div>
        </div>
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          className="rounded-full border border-slate-200 bg-white px-4.5 py-2 text-sm font-bold text-slate-800"
        >
          Browse files
        </button>
        <input
          ref={inputRef}
          type="file"
          accept=".pdf,.docx,.jpg,.jpeg,.png"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) onFileSelected(file);
          }}
        />
      </div>
      <p className="mt-3 text-xs text-slate-400">
        Uploading runs in the background — you can keep chatting or close this and do something else while it works.
      </p>
    </Modal>
  );
}
