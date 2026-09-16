import type { ReactNode } from "react";
import { IconClose } from "./icons";

interface Props {
  title: string;
  subtitle?: string;
  width?: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
}

export default function Modal({ title, subtitle, width = "520px", onClose, children, footer }: Props) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-brand-navy/55 p-3 sm:p-6"
      onClick={onClose}
    >
      <div
        className="flex w-full max-h-[90vh] flex-col overflow-hidden rounded-3xl bg-white shadow-2xl"
        style={{ maxWidth: width }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-4 border-b border-slate-200 px-5 py-4 sm:px-7 sm:py-5">
          <div>
            <div className="font-semibold text-lg text-brand-navy">{title}</div>
            {subtitle && <div className="mt-1 text-sm text-slate-500">{subtitle}</div>}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="flex h-8 w-8 flex-none items-center justify-center rounded-full border border-slate-200 text-slate-400 hover:bg-slate-50"
            aria-label="Close"
          >
            <IconClose />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-5 sm:px-7 sm:py-6">{children}</div>

        {footer && <div className="flex flex-col-reverse justify-end gap-2.5 border-t border-slate-200 px-5 py-4 sm:flex-row sm:px-7">{footer}</div>}
      </div>
    </div>
  );
}
