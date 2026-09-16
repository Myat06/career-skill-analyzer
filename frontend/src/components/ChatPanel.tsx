import { useEffect, useRef, useState } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { IconAttach, IconCheck, IconSend, IconSparkle, IconSpinner } from "./icons";

// Assistant replies are LLM prose that may use markdown (bold, lists, and --
// per consultation_chat.py's system prompt -- tables for multi-attribute
// comparisons like matched competencies or recommended courses). These
// overrides restyle each element to match the chat bubble's existing slate/
// navy look rather than using browser-default markdown styling, which would
// look out of place next to the rest of the UI.
const MARKDOWN_COMPONENTS: Components = {
  p: ({ children }) => <p className="my-1.5 first:mt-0 last:mb-0">{children}</p>,
  strong: ({ children }) => <strong className="font-bold text-slate-900">{children}</strong>,
  ul: ({ children }) => <ul className="my-1.5 list-disc space-y-1 pl-5">{children}</ul>,
  ol: ({ children }) => <ol className="my-1.5 list-decimal space-y-1 pl-5">{children}</ol>,
  li: ({ children }) => <li className="leading-relaxed">{children}</li>,
  a: ({ children, href }) => (
    <a href={href} target="_blank" rel="noreferrer" className="text-brand-navy underline underline-offset-2">
      {children}
    </a>
  ),
  code: ({ children }) => (
    <code className="rounded bg-slate-100 px-1 py-0.5 font-mono text-xs text-slate-700">{children}</code>
  ),
  table: ({ children }) => (
    <div className="my-2 overflow-x-auto rounded-lg border border-slate-200">
      <table className="w-full border-collapse text-xs sm:text-sm">{children}</table>
    </div>
  ),
  thead: ({ children }) => <thead className="bg-slate-100">{children}</thead>,
  th: ({ children }) => (
    <th className="border-b border-slate-200 px-2.5 py-1.5 text-left font-bold text-slate-700">{children}</th>
  ),
  td: ({ children }) => <td className="border-b border-slate-100 px-2.5 py-1.5 align-top">{children}</td>,
};

function AssistantMarkdown({ content }: { content: string }) {
  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={MARKDOWN_COMPONENTS}>
      {content}
    </ReactMarkdown>
  );
}

export interface DisplayMessage {
  id: string;
  role: "user" | "assistant" | "system" | "progress";
  content: string;
  fileName?: string;
  // Set when an "assistant" reply came back from a degraded/unavailable AI call
  // (see ConsultResponse.status) -- the reply text is still shown, just with a
  // visual cue that it may be a canned fallback rather than a grounded answer.
  degraded?: boolean;
}

interface Props {
  messages: DisplayMessage[];
  sending: boolean;
  onSend: (text: string) => void;
  onAttachClick: () => void;
  hasResume: boolean;
  hasActivities: boolean;
  hasRole: boolean;
}

const SUGGESTED_QUESTIONS = [
  "Which courses should I prioritize next semester?",
  "How do I explain a resume gap in an interview?",
];

function joinNatural(items: string[]): string {
  if (items.length <= 1) return items[0] ?? "";
  if (items.length === 2) return `${items[0]} or ${items[1]}`;
  return `${items.slice(0, -1).join(", ")}, or ${items[items.length - 1]}`;
}

// Only names what's actually still missing -- a student who's already
// uploaded a resume and logged activities shouldn't be told to do those
// again just because they haven't sent a chat message yet.
function buildEmptyStateHint(hasResume: boolean, hasActivities: boolean, hasRole: boolean): string {
  const missing = [
    !hasResume && "upload your resume",
    !hasActivities && "log an activity",
    !hasRole && "set a target role",
  ].filter((step): step is string => !!step);
  const askPart = "Ask me about your career readiness, resume, or skill gaps";
  if (missing.length === 0) return `${askPart}.`;
  return `${askPart}, or get started by ${joinNatural(missing)}.`;
}

export default function ChatPanel({ messages, sending, onSend, onAttachClick, hasResume, hasActivities, hasRole }: Props) {
  const [draft, setDraft] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, sending]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const text = draft.trim();
    if (!text || sending) return;
    onSend(text);
    setDraft("");
  };

  return (
    <div className="flex h-[min(760px,calc(100vh-260px))] min-h-100 w-full flex-1 flex-col overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-sm lg:h-[min(820px,calc(100vh-200px))]">
      <div className="flex items-center gap-3 border-b border-slate-200 px-5.5 py-4.5">
        <span className="flex h-9 w-9 flex-none items-center justify-center rounded-xl bg-brand-navy text-white">
          <IconSparkle size={17} />
        </span>
        <div>
          <div className="text-sm font-bold text-slate-900">Compass Coach</div>
          <div className="text-xs text-slate-400">Grounded in your profile, resume, and skill-gap analysis</div>
        </div>
      </div>

      <div ref={scrollRef} className="flex flex-1 flex-col gap-4.5 overflow-y-auto px-6 py-6">
        {messages.length === 0 && (
          <div className="m-auto flex max-w-xs flex-col items-center gap-2 text-center">
            <p className="text-sm font-bold text-slate-700">Welcome to the Compass Coach AI Chat.</p>
            <p className="mb-2 text-sm text-slate-400">{buildEmptyStateHint(hasResume, hasActivities, hasRole)}</p>
            <div className="flex w-full flex-col gap-2">
              {SUGGESTED_QUESTIONS.map((question) => (
                <button
                  type="button"
                  key={question}
                  onClick={() => onSend(question)}
                  className="rounded-xl border border-slate-200 px-3.5 py-2.5 text-left text-xs font-semibold text-slate-500 hover:bg-slate-50"
                >
                  {question}
                </button>
              ))}
            </div>
          </div>
        )}
        {messages.map((m) => {
          if (m.role === "system") {
            return (
              <div key={m.id} className="flex gap-2.5">
                <span className="flex h-7 w-7 flex-none items-center justify-center rounded-lg bg-brand-navy-soft text-brand-navy-strong">
                  <IconSparkle size={14} />
                </span>
                <div className="flex max-w-[85%] items-center gap-2 rounded-2xl rounded-tl-md bg-slate-50 px-4 py-3 text-sm leading-relaxed text-slate-800 sm:max-w-[72%]">
                  <IconCheck className="flex-none text-emerald-500" />
                  {m.content}
                </div>
              </div>
            );
          }
          if (m.role === "progress") {
            return (
              <div key={m.id} className="flex gap-2.5">
                <span className="flex h-7 w-7 flex-none items-center justify-center rounded-lg bg-brand-navy-soft text-brand-navy-strong">
                  <IconSparkle size={14} />
                </span>
                <div className="flex items-center gap-2 rounded-2xl rounded-tl-md bg-slate-50 px-4 py-3 text-sm text-slate-500">
                  <IconSpinner className="text-brand-navy" />
                  {m.content}
                </div>
              </div>
            );
          }
          if (m.role === "user") {
            return (
              <div key={m.id} className="flex justify-end">
                <div className="max-w-[85%] rounded-2xl rounded-tr-md bg-brand-navy-soft px-4 py-3 text-sm leading-relaxed text-brand-navy sm:max-w-[70%]">
                  {m.fileName && (
                    <div className="mb-2 flex items-center gap-2 rounded-lg bg-white/60 px-2.5 py-1.5 text-xs font-bold">
                      {m.fileName}
                    </div>
                  )}
                  {m.content}
                </div>
              </div>
            );
          }
          return (
            <div key={m.id} className="flex gap-2.5">
              <span
                className={`flex h-7 w-7 flex-none items-center justify-center rounded-lg ${
                  m.degraded ? "bg-amber-100 text-amber-700" : "bg-brand-navy-soft text-brand-navy-strong"
                }`}
              >
                <IconSparkle size={14} />
              </span>
              <div
                className={`max-w-[85%] rounded-2xl rounded-tl-md px-4 py-3 text-sm leading-relaxed sm:max-w-[72%] ${
                  m.degraded ? "border border-amber-200 bg-amber-50 text-amber-900" : "bg-slate-50 text-slate-800"
                }`}
              >
                <AssistantMarkdown content={m.content} />
              </div>
            </div>
          );
        })}
        {sending && (
          <div className="flex gap-2.5">
            <span className="flex h-7 w-7 flex-none items-center justify-center rounded-lg bg-brand-navy-soft text-brand-navy-strong">
              <IconSparkle size={14} />
            </span>
            <div className="flex items-center gap-2 rounded-2xl rounded-tl-md bg-slate-50 px-4 py-3 text-sm text-slate-500">
              <IconSpinner className="text-brand-navy" />
              Thinking…
            </div>
          </div>
        )}
      </div>

      <form onSubmit={handleSubmit} className="flex items-center gap-2 px-5.5 pb-5.5 pt-1">
        <button
          type="button"
          onClick={onAttachClick}
          className="flex h-9.5 w-9.5 flex-none items-center justify-center rounded-full border border-slate-200 text-slate-500 hover:bg-slate-50"
          aria-label="Attach a file"
        >
          <IconAttach />
        </button>
        <div className="flex flex-1 items-center gap-2 rounded-full border border-slate-200 bg-slate-50 py-1.5 pl-4.5 pr-1.5">
          <input
            className="flex-1 bg-transparent text-sm text-slate-800 outline-none placeholder:text-slate-400"
            placeholder="Ask about your career path, or attach a file…"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
          />
          <button
            type="submit"
            disabled={sending || !draft.trim()}
            className="flex h-9.5 w-9.5 flex-none items-center justify-center rounded-full bg-brand-navy text-white disabled:opacity-40"
            aria-label="Send"
          >
            <IconSend />
          </button>
        </div>
      </form>
    </div>
  );
}
