type IconProps = { className?: string; size?: number };

const base = (size: number) => ({
  viewBox: "0 0 24 24",
  width: size,
  height: size,
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.7,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
});

export function IconClose({ className, size = 14 }: IconProps) {
  return (
    <svg {...base(size)} className={className}>
      <path d="M6 6l12 12M18 6L6 18" />
    </svg>
  );
}

export function IconUpload({ className, size = 17 }: IconProps) {
  return (
    <svg {...base(size)} className={className}>
      <path d="M12 16V5M8 9l4-4 4 4" />
      <path d="M4.5 15.5v2.5a2 2 0 0 0 2 2h11a2 2 0 0 0 2-2v-2.5" />
    </svg>
  );
}

export function IconActivity({ className, size = 17 }: IconProps) {
  return (
    <svg {...base(size)} className={className}>
      <path d="M3.5 7.5a1.5 1.5 0 0 1 1.5-1.5h4l2 2h8a1.5 1.5 0 0 1 1.5 1.5v8a1.5 1.5 0 0 1-1.5 1.5H5a1.5 1.5 0 0 1-1.5-1.5Z" />
      <path d="M12 11v5M9.5 13.5h5" />
    </svg>
  );
}

export function IconReport({ className, size = 17 }: IconProps) {
  return (
    <svg {...base(size)} className={className}>
      <rect x="5" y="4.5" width="14" height="16" rx="1.5" />
      <path d="M9 3.5h6a1 1 0 0 1 1 1v1H8v-1a1 1 0 0 1 1-1Z" />
      <path d="M8.5 12l2 2 4-4.2" />
    </svg>
  );
}

export function IconPoster({ className, size = 17 }: IconProps) {
  return (
    <svg {...base(size)} className={className}>
      <rect x="3.5" y="4.5" width="17" height="15" rx="1.5" />
      <circle cx="9" cy="10" r="1.6" fill="currentColor" stroke="none" />
      <path d="M4 17l4.5-4.5a1.5 1.5 0 0 1 2.1 0L14 16l1.6-1.6a1.5 1.5 0 0 1 2.1 0L20.5 17" />
    </svg>
  );
}

export function IconSend({ className, size = 17 }: IconProps) {
  return (
    <svg {...base(size)} className={className}>
      <path d="M4 12 20 4l-6 16-3-6-7-2Z" />
    </svg>
  );
}

export function IconAttach({ className, size = 16 }: IconProps) {
  return (
    <svg {...base(size)} className={className}>
      <path d="M7 12.5l6.5-6.5a4 4 0 0 1 5.7 5.7L11 20a2.5 2.5 0 0 1-3.5-3.5l7-7" />
    </svg>
  );
}

export function IconSparkle({ className, size = 14 }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" width={size} height={size} fill="currentColor" stroke="none" className={className}>
      <path d="M12 3l1.6 5.4L19 10l-5.4 1.6L12 17l-1.6-5.4L5 10l5.4-1.6Z" />
    </svg>
  );
}

export function IconCheck({ className, size = 15 }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" width={size} height={size} fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" className={className}>
      <circle cx="12" cy="12" r="9" />
      <path d="M8.5 12.5l2.5 2.5 5-5" />
    </svg>
  );
}

export function IconChevronRight({ className, size = 15 }: IconProps) {
  return (
    <svg {...base(size)} className={className}>
      <path d="M9 6l6 6-6 6" />
    </svg>
  );
}

export function IconSearch({ className, size = 16 }: IconProps) {
  return (
    <svg {...base(size)} className={className}>
      <circle cx="11" cy="11" r="6.5" />
      <path d="M20 20l-4.5-4.5" />
    </svg>
  );
}

export function IconSpinner({ className, size = 14 }: IconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      fill="none"
      className={`animate-spin ${className ?? ""}`}
    >
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2.5" opacity="0.2" />
      <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
    </svg>
  );
}

export function IconPanel({ className, size = 15 }: IconProps) {
  return (
    <svg {...base(size)} className={className}>
      <rect x="3.5" y="4.5" width="17" height="15" rx="2" />
      <path d="M14.5 4.5v15" />
    </svg>
  );
}

export function IconPlus({ className, size = 15 }: IconProps) {
  return (
    <svg {...base(size)} className={className}>
      <path d="M12 5v14M5 12h14" />
    </svg>
  );
}

export function IconMenu({ className, size = 15 }: IconProps) {
  return (
    <svg {...base(size)} className={className}>
      <path d="M4 6h16M4 12h16M4 18h16" />
    </svg>
  );
}

export function IconPin({ className, size = 13 }: IconProps) {
  return (
    <svg {...base(size)} className={className}>
      <path d="M9 4.5h6l-.7 5.2 3.2 3.3H13v6l-1 2-1-2v-6H6.5l3.2-3.3z" />
    </svg>
  );
}

export function IconTrash({ className, size = 13 }: IconProps) {
  return (
    <svg {...base(size)} className={className}>
      <path d="M4.5 7h15M9.5 7V5a1.5 1.5 0 0 1 1.5-1.5h2A1.5 1.5 0 0 1 14.5 5v2M18 7l-.8 12a2 2 0 0 1-2 1.8H8.8a2 2 0 0 1-2-1.8L6 7" />
    </svg>
  );
}

