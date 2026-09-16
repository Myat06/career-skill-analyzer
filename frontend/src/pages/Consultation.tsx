import { useEffect, useRef, useState } from "react";
import { useStudentContext } from "../StudentContext";
import { useChatSessionContext } from "../ChatSessionContext";
import { studentsApi } from "../api/students";
import { analyzerApi } from "../api/analyzer";
import { resumesApi } from "../api/resumes";
import { chatSessionsApi } from "../api/chatSessions";
import { consultationApi, reportsApi, type ChatMessage } from "../api/consultation";
import ChatPanel, { type DisplayMessage } from "../components/ChatPanel";
import ContextPanel from "../components/ContextPanel";
import { IconChevronRight, IconPanel } from "../components/icons";
import RoleSelectModal from "../components/RoleSelectModal";
import UploadResumeModal from "../components/UploadResumeModal";
import AddActivityModal from "../components/AddActivityModal";
import ConfirmGenerateModal from "../components/ConfirmGenerateModal";
import { buildRoleBriefing } from "../lib/roleBriefing";
import { buildGeneratedBriefing } from "../lib/generatedBriefing";
import type { ActivityOut, JobRole, SkillGapResponse } from "../types";

async function downloadFile(url: string, filename: string) {
  const response = await fetch(url);
  if (!response.ok) {
    const detail = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(detail.detail ?? response.statusText);
  }
  const blob = await response.blob();
  const objectUrl = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(objectUrl);
}

type RoleIntent = "report" | "poster" | "set" | null;

function newId() {
  return Math.random().toString(36).slice(2);
}

export default function Consultation() {
  const { selectedStudent } = useStudentContext();
  const { activeSessionId, setActiveSessionId, refreshSessions } = useChatSessionContext();

  const [activities, setActivities] = useState<ActivityOut[]>([]);
  const [resumeInfo, setResumeInfo] = useState<{ id: string; fileName: string; overallScore: number | null } | null>(
    null
  );
  const [uploadingResume, setUploadingResume] = useState(false);
  const [currentJobRole, setCurrentJobRole] = useState<JobRole | null>(null);
  const [skillGap, setSkillGap] = useState<SkillGapResponse | null>(null);
  const [analyzingRole, setAnalyzingRole] = useState(false);

  const [chatHistory, setChatHistory] = useState<ChatMessage[]>([]);
  const [displayMessages, setDisplayMessages] = useState<DisplayMessage[]>([]);
  const [sending, setSending] = useState(false);

  const [roleModalIntent, setRoleModalIntent] = useState<RoleIntent>(null);
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [showActivityModal, setShowActivityModal] = useState(false);
  const [confirmGenerate, setConfirmGenerate] = useState<{ mode: "report" | "poster"; jobRole: JobRole } | null>(
    null
  );
  const [generatingMode, setGeneratingMode] = useState<"report" | "poster" | null>(null);
  const [showContext, setShowContext] = useState(true);
  // React state updates from two clicks in the same tick aren't guaranteed to be visible
  // to each other yet -- a ref gives a synchronous, immediate guard against a genuine
  // double-click firing generateAndDownload twice, the same pattern activeStudentIdRef
  // uses below for cross-render race safety.
  const generatingRef = useRef(false);

  // Every background operation below (resume scoring, skill-gap analysis, report
  // generation) can easily outlive the student it was started for -- these are 60-150s
  // LLM calls, and nothing stops someone from switching students mid-flight. This ref
  // always holds the CURRENTLY viewed student's id (updated synchronously below,
  // unlike the `selectedStudent` each async closure captured at call time), so every
  // continuation can check "is this still who I was doing this for?" before writing
  // its result into the chat/context panel. Without that check, a slow operation for
  // student A resolves late and silently paints its result onto student B's screen --
  // A's data was never touched in the database, but B's UI would lie about it.
  const activeStudentIdRef = useRef<string | null>(null);

  // Which saved session's content is currently reflected in displayMessages/
  // chatHistory -- null means "an unsaved fresh draft" (either a brand-new
  // chat that hasn't been typed in yet, or one that hasn't been saved for
  // the first time). Compared against activeSessionId (from
  // ChatSessionContext, which the sidebar's New Chat button / history list
  // set) to tell "nothing to do" apart from "load a different session" --
  // see the effect below.
  const loadedSessionIdRef = useRef<string | null>(null);
  // Set right before populating state from a fetched session, so the
  // autosave effect below can tell "this change came from loading a past
  // session" apart from "this change is new content that needs saving" and
  // skip saving the former straight back to itself.
  const loadingSessionRef = useRef(false);

  useEffect(() => {
    if (!selectedStudent) return;
    const studentId = selectedStudent.id;
    activeStudentIdRef.current = studentId;
    loadedSessionIdRef.current = null;

    setActivities([]);
    setResumeInfo(null);
    setUploadingResume(false);
    setAnalyzingRole(false);
    setCurrentJobRole(null);
    setSkillGap(null);
    setChatHistory([]);
    setDisplayMessages([]);
    setSending(false);
    setGeneratingMode(null);
    setConfirmGenerate(null);

    studentsApi
      .profile(studentId)
      .then((p) => {
        if (activeStudentIdRef.current === studentId) setActivities(p.activities);
      })
      .catch(() => {});

    // Restore the latest uploaded resume, if any -- same reload-amnesia problem as the
    // target role below: without this, Generate would wrongly think no resume exists
    // and block a student who already uploaded one in an earlier session. Normalized to
    // resolve with null (rather than rejecting) so the skill-gap staleness check below
    // can await it without a 404 there aborting that chain too.
    const latestResume = resumesApi.latest(studentId).then(
      (resume) => resume,
      () => null,
    );
    latestResume.then((resume) => {
      if (activeStudentIdRef.current === studentId && resume) {
        setResumeInfo({ id: resume.id, fileName: resume.original_filename ?? "resume", overallScore: null });
      }
    });

    // Restore the most recently analyzed target role, if any -- without this, a page
    // reload "forgets" the role and the next resume upload/chat message silently goes
    // out role-less again, even though the backend already has a real analysis for it.
    // The match/matched/partial/missing numbers are only restored alongside it if the
    // resume they were scored against is still the current one -- same staleness check
    // as handleRemoveResume/handleFileSelected, needed here too since a page reload
    // bypasses that in-session state entirely and re-fetches from scratch.
    analyzerApi
      .history(studentId)
      .then(async (history) => {
        const latest = history[0];
        if (!latest) return;
        const [full, resume] = await Promise.all([analyzerApi.getSkillGap(latest.id), latestResume]);
        if (activeStudentIdRef.current !== studentId) return;
        setCurrentJobRole(full.job_role);
        const stale = !resume || new Date(resume.created_at) > new Date(latest.created_at);
        if (!stale) setSkillGap(full);
      })
      .catch(() => {});
  }, [selectedStudent]);

  // Reacts to the sidebar's New Chat button / history-list clicks (both just
  // set activeSessionId via ChatSessionContext). Comparing against
  // loadedSessionIdRef -- not a plain "did activeSessionId change" check --
  // is what lets the autosave effect below set activeSessionId on a fresh
  // create without this effect turning around and re-fetching what was just
  // saved.
  useEffect(() => {
    if (!selectedStudent) return;
    if (activeSessionId === loadedSessionIdRef.current) return;

    if (activeSessionId === null) {
      // New Chat: a fresh conversation thread for the same student profile,
      // unlike a full student switch -- role/resume/activities stay put.
      loadedSessionIdRef.current = null;
      setChatHistory([]);
      setDisplayMessages([]);
      return;
    }

    const studentId = selectedStudent.id;
    const sessionId = activeSessionId;
    chatSessionsApi
      .get(studentId, sessionId)
      .then((full) => {
        if (activeStudentIdRef.current !== studentId) return;
        loadingSessionRef.current = true;
        loadedSessionIdRef.current = sessionId;
        setDisplayMessages(full.display_messages);
        setChatHistory(full.chat_history);
        if (full.job_role) setCurrentJobRole(full.job_role);
        // Deliberately not restored: the live matched/partial/missing state
        // (skillGap) behind this session's target role. That's expensive,
        // staleness-checked data (see the resume-upload/role-confirm
        // handlers below) -- the reloaded chat content already shows what
        // was said, and re-running the analysis is one click away via the
        // context panel if the student wants current numbers.
        setSkillGap(null);
      })
      .catch(() => {
        pushSystemNote("Couldn't load that chat — try again.");
      });
  }, [activeSessionId, selectedStudent]);

  // Debounced autosave: fires whenever displayMessages actually changes
  // (always the latest committed state, unlike reading state right after a
  // setState call inside a handler -- several handlers below update via the
  // setX(prev => ...) functional form, so there's no synchronous local copy
  // of the final array to save explicitly at each call site instead).
  useEffect(() => {
    if (!selectedStudent) return;
    if (displayMessages.length === 0) return;
    if (loadingSessionRef.current) {
      // This change came from loading a past session, not new content --
      // nothing to save, it's already saved.
      loadingSessionRef.current = false;
      return;
    }
    const studentId = selectedStudent.id;
    const timer = window.setTimeout(() => {
      const payload = {
        display_messages: displayMessages,
        chat_history: chatHistory,
        job_role_id: currentJobRole?.id ?? null,
      };
      const save = loadedSessionIdRef.current
        ? chatSessionsApi.update(studentId, loadedSessionIdRef.current, payload)
        : chatSessionsApi.create(studentId, payload);
      save
        .then((saved) => {
          if (activeStudentIdRef.current !== studentId) return;
          // Set loadedSessionIdRef BEFORE setActiveSessionId so the effect
          // above sees them already equal on the next render and skips
          // re-fetching what was just saved.
          loadedSessionIdRef.current = saved.id;
          if (activeSessionId !== saved.id) setActiveSessionId(saved.id);
          refreshSessions();
        })
        .catch(() => {
          // Best-effort -- a failed save just means this turn isn't in
          // history yet; the live conversation itself is unaffected, same
          // as other non-critical failures elsewhere in this file.
        });
    }, 500);
    return () => window.clearTimeout(timer);
    // chatHistory/currentJobRole/activeSessionId/setActiveSessionId/refreshSessions are
    // read inside the timeout, not watched -- only a genuine displayMessages
    // change should schedule a new save.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [displayMessages]);

  if (!selectedStudent) {
    return <p className="text-sm text-slate-400">Loading student…</p>;
  }

  const pushSystemNote = (content: string) => {
    setDisplayMessages((prev) => {
      // A repeated click on a gated action (e.g. "Choose role" with no resume
      // yet) would otherwise stack up identical notes back to back -- collapse
      // that into a single note instead of restating it.
      const last = prev[prev.length - 1];
      if (last && last.role === "system" && last.content === content) return prev;
      return [...prev, { id: newId(), role: "system", content }];
    });
  };

  const pushAssistantMessage = (content: string) => {
    setDisplayMessages((prev) => [...prev, { id: newId(), role: "assistant", content }]);
  };

  const pushProgress = (id: string, content: string) => {
    setDisplayMessages((prev) => [...prev, { id, role: "progress", content }]);
  };
  const updateProgress = (id: string, content: string) => {
    setDisplayMessages((prev) => prev.map((m) => (m.id === id ? { ...m, content } : m)));
  };
  const clearProgress = (id: string) => {
    setDisplayMessages((prev) => prev.filter((m) => m.id !== id));
  };

  const sendMessage = async (text: string, fileName?: string) => {
    const studentId = selectedStudent.id;
    const userDisplay: DisplayMessage = { id: newId(), role: "user", content: text, fileName };
    setDisplayMessages((prev) => [...prev, userDisplay]);
    const nextHistory: ChatMessage[] = [...chatHistory, { role: "user", content: text }];
    setChatHistory(nextHistory);
    setSending(true);
    try {
      const result = await consultationApi.send(studentId, nextHistory, currentJobRole?.id);
      if (activeStudentIdRef.current !== studentId) return;
      setDisplayMessages((prev) => [
        ...prev,
        { id: newId(), role: "assistant", content: result.reply, degraded: result.status !== "ok" },
      ]);
      setChatHistory((prev) => [...prev, { role: "assistant", content: result.reply }]);
    } catch (err) {
      if (activeStudentIdRef.current !== studentId) return;
      setDisplayMessages((prev) => [
        ...prev,
        {
          id: newId(),
          role: "assistant",
          content: err instanceof Error ? err.message : "Something went wrong.",
          degraded: true,
        },
      ]);
    } finally {
      if (activeStudentIdRef.current === studentId) setSending(false);
    }
  };

  const generateAndDownload = async (mode: "report" | "poster", jobRole: JobRole, studentId: string, studentNo: string) => {
    // Belt-and-suspenders against a double-click or a stray second call: the ref check
    // is synchronous (immune to React batching two same-tick clicks), the disabled
    // button is the first line of defense, this is the fallback if that's ever bypassed.
    if (generatingRef.current) return;
    generatingRef.current = true;
    setGeneratingMode(mode);

    const label = mode === "report" ? "consultation report" : "Expo poster";
    const progressId = newId();
    pushProgress(progressId, `Analyzing your profile, resume, and skill match for the ${label}…`);
    const stageTimer = window.setTimeout(() => {
      if (activeStudentIdRef.current === studentId) updateProgress(progressId, `Generating your ${label}…`);
    }, 6000);
    try {
      const url =
        mode === "report" ? reportsApi.reportPdfUrl(studentId, jobRole.id) : reportsApi.posterPngUrl(studentId, jobRole.id);
      const filename =
        mode === "report" ? `${studentNo}-consultation-report.pdf` : `${studentNo}-consultation-poster.png`;
      // The download itself always proceeds -- it's tied to the original student/role by
      // URL, not by whatever is on screen now, so it's correct regardless of a switch.
      await downloadFile(url, filename);
      window.clearTimeout(stageTimer);
      if (activeStudentIdRef.current !== studentId) return;
      clearProgress(progressId);
      pushSystemNote(`Your ${label} is ready — check your downloads.`);
      // Surface what the report actually says. This is a cache hit on the work
      // the download just did, so it adds no model time -- but it must never be
      // able to make a successful download look like a failure, hence the
      // separate try/catch that degrades to silence.
      try {
        const summary = await reportsApi.summary(studentId, jobRole.id);
        if (activeStudentIdRef.current !== studentId) return;
        pushAssistantMessage(buildGeneratedBriefing(mode, summary));
      } catch {
        // The file is already downloaded and the note above says so; a failure
        // to fetch the recap is not worth an error message.
      }
    } catch (err) {
      window.clearTimeout(stageTimer);
      if (activeStudentIdRef.current !== studentId) return;
      clearProgress(progressId);
      pushSystemNote(err instanceof Error ? err.message : `Couldn't generate the ${label} — try again.`);
    } finally {
      generatingRef.current = false;
      if (activeStudentIdRef.current === studentId) setGeneratingMode(null);
    }
  };

  const handleRoleConfirm = async (role: JobRole) => {
    const studentId = selectedStudent.id;
    const studentNo = selectedStudent.student_no;
    const intent = roleModalIntent;
    setRoleModalIntent(null);
    setAnalyzingRole(true);
    const progressId = newId();
    pushProgress(progressId, `Analyzing your match against ${role.role_title}…`);
    try {
      const result = await analyzerApi.runSkillGap(studentId, { job_role_id: role.id });
      if (activeStudentIdRef.current !== studentId) return;
      setSkillGap(result);
      setCurrentJobRole(role);
      clearProgress(progressId);
      // runSkillGap already produced a citation-checked narrative as part of
      // that call; surface it as a real briefing instead of discarding it.
      // Its own opening line already states the role and match %, so no
      // separate "Target role set to X" note is needed above it.
      pushAssistantMessage(buildRoleBriefing(result));
      if (intent === "report" || intent === "poster") void generateAndDownload(intent, role, studentId, studentNo);
    } catch (err) {
      if (activeStudentIdRef.current !== studentId) return;
      clearProgress(progressId);
      pushSystemNote(err instanceof Error ? err.message : "Couldn't analyze that role — try again.");
    } finally {
      if (activeStudentIdRef.current === studentId) setAnalyzingRole(false);
    }
  };

  const handleRemoveResume = async (resumeId: string) => {
    const studentId = selectedStudent.id;
    const fileName = resumeInfo?.fileName ?? "Resume";
    // Unhandled before: when the request failed the rejection propagated out of
    // the click handler, so the resume simply stayed on screen with no message
    // at all -- indistinguishable from the button not working.
    try {
      await resumesApi.remove(studentId, resumeId);
    } catch (err) {
      if (activeStudentIdRef.current !== studentId) return;
      pushSystemNote(
        err instanceof Error ? `Couldn't remove ${fileName}: ${err.message}` : `Couldn't remove ${fileName} — try again.`,
      );
      return;
    }
    if (activeStudentIdRef.current !== studentId) return;
    const hadJobRole = currentJobRole;
    setResumeInfo(null);
    // The removed resume was part of the evidence corpus behind any skill-gap
    // match already computed for currentJobRole -- drop the stale match
    // percentage and matched/partial/missing counts rather than let them keep
    // showing a result that no longer reflects the student's actual evidence.
    // The target role itself is cleared too, rather than left showing with no
    // score behind it -- the student picks a role again once they have a resume.
    setSkillGap(null);
    setCurrentJobRole(null);
    pushSystemNote(
      hadJobRole
        ? `${fileName} removed from your profile — upload a new resume and choose your target role again to re-run the match.`
        : `${fileName} removed from your profile`,
    );
  };

  /**
   * The resume is the one piece of evidence the student supplies by hand, and
   * every downstream output leans on it: the skill-gap engine scores it as
   * evidence, and the report and poster both carry a resume score. Gate the
   * whole flow on it rather than only the final download, so a student can't
   * get several minutes into an analysis before being told a resume was
   * needed all along.
   */
  const requireResume = (reason: string): boolean => {
    if (resumeInfo) return true;
    pushSystemNote(`Please upload your resume first — ${reason}`);
    setShowUploadModal(true);
    return false;
  };

  const requireResumeThenChooseRole = () => {
    if (requireResume("I'll score your skill match against it, along with your courses and activities.")) {
      setRoleModalIntent("set");
    }
  };

  const requireResumeThenGenerate = (mode: "report" | "poster") => {
    if (generatingRef.current) return; // already generating -- ignore a stray extra click
    if (!requireResume(`your ${mode === "report" ? "consultation report" : "Expo poster"} includes a resume score.`)) {
      return;
    }
    if (currentJobRole) {
      // A misclick here kicks off a multi-minute generation that auto-downloads a
      // file -- cheap to confirm, expensive to accidentally trigger twice.
      setConfirmGenerate({ mode, jobRole: currentJobRole });
    } else {
      setRoleModalIntent(mode);
    }
  };

  const handleConfirmGenerate = () => {
    if (!confirmGenerate) return;
    const { mode, jobRole } = confirmGenerate;
    setConfirmGenerate(null);
    void generateAndDownload(mode, jobRole, selectedStudent.id, selectedStudent.student_no);
  };

  const handleFileSelected = async (file: File) => {
    const studentId = selectedStudent.id;
    setShowUploadModal(false);
    setUploadingResume(true);
    const jobRoleId = currentJobRole?.id;
    const jobRoleTitle = currentJobRole?.role_title;
    const progressId = newId();
    pushProgress(progressId, `Uploading ${file.name}…`);
    try {
      const resume = await resumesApi.upload(studentId, file);
      if (activeStudentIdRef.current === studentId) updateProgress(progressId, "Analyzing your resume…");
      let overallScore: number | null = null;
      let nameMismatch = false;
      try {
        const score = await resumesApi.score(resume.id, jobRoleId);
        overallScore = score.overall_score;
        // Same phrase resume_score.py uses for its own PRIORITY chat instruction --
        // surfacing it here too means the student sees a plain, natural heads-up
        // right away, instead of only however the AI happens to word it once it
        // gets around to answering (and possibly buried under a skill-gap answer
        // if one was already in progress).
        nameMismatch = !!score.note?.includes("doesn't match your registered name");
      } catch {
        overallScore = null; // scoring can fail independently (e.g. AI service down); upload still counts
      }
      if (activeStudentIdRef.current !== studentId) return;
      setResumeInfo({ id: resume.id, fileName: resume.original_filename ?? "resume", overallScore });
      // Same staleness concern as removal: this resume is new evidence, so any
      // skill-gap match already computed for currentJobRole no longer reflects it.
      if (currentJobRole) setSkillGap(null);
      clearProgress(progressId);
      pushSystemNote(`${resume.original_filename ?? "Your resume"} added to your profile`);
      if (nameMismatch) {
        pushSystemNote(
          "Just double-checking — the name on this resume doesn't look like it matches your " +
            "registered name. Is this definitely your own resume? If not, remove it and upload " +
            "the right one from the upload panel.",
        );
      }
      void sendMessage(
        jobRoleTitle ? `Can you check this against ${jobRoleTitle}?` : "Can you take a look at my resume?",
        resume.original_filename ?? undefined
      );
    } catch (err) {
      if (activeStudentIdRef.current !== studentId) return;
      clearProgress(progressId);
      pushSystemNote(err instanceof Error ? err.message : "Resume upload failed — try again.");
    } finally {
      if (activeStudentIdRef.current === studentId) setUploadingResume(false);
    }
  };

  return (
    <div className="flex flex-1 flex-col gap-5.5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-brand-navy sm:text-3xl">AI Consultation</h1>
          <p className="mt-1 text-sm text-slate-500">Grounded answers, drawn from your own analysis data.</p>
        </div>
        <button
          type="button"
          onClick={() => setShowContext((v) => !v)}
          className={`flex flex-none items-center gap-1.5 rounded-full border px-3.5 py-2 text-sm font-semibold transition-colors ${
            showContext
              ? "border-brand-blue bg-brand-blue-soft text-brand-blue"
              : "border-slate-200 bg-white text-slate-600 hover:border-slate-300"
          }`}
        >
          <IconPanel size={15} />
          <span className="hidden sm:inline">Profile &amp; Tools</span>
          <IconChevronRight size={13} className={`transition-transform ${showContext ? "rotate-90" : ""}`} />
        </button>
      </div>

      <div className="flex flex-col items-stretch gap-5 lg:flex-row lg:items-start">
        <ChatPanel
          messages={displayMessages}
          sending={sending}
          onSend={(text) => void sendMessage(text)}
          onAttachClick={() => setShowUploadModal(true)}
          hasResume={!!resumeInfo}
          hasActivities={activities.length > 0}
          hasRole={!!currentJobRole}
        />
        {showContext && (
          <ContextPanel
            skillGap={skillGap}
            currentJobRole={currentJobRole}
            analyzingRole={analyzingRole}
            resumeInfo={resumeInfo}
            uploadingResume={uploadingResume}
            activitiesCount={activities.length}
            generatingMode={generatingMode}
            onUploadResume={() => setShowUploadModal(true)}
            onAddActivity={() => setShowActivityModal(true)}
            onChooseRole={requireResumeThenChooseRole}
            onGenerateReport={() => requireResumeThenGenerate("report")}
            onGeneratePoster={() => requireResumeThenGenerate("poster")}
          />
        )}
      </div>

      {confirmGenerate && (
        <ConfirmGenerateModal
          mode={confirmGenerate.mode}
          jobRole={confirmGenerate.jobRole}
          onClose={() => setConfirmGenerate(null)}
          onConfirm={handleConfirmGenerate}
        />
      )}

      {roleModalIntent && (
        <RoleSelectModal
          currentJobRole={currentJobRole}
          currentMatchPercentage={skillGap?.match_percentage ?? null}
          onClose={() => setRoleModalIntent(null)}
          onConfirm={(role) => void handleRoleConfirm(role)}
        />
      )}

      {showUploadModal && (
        <UploadResumeModal
          currentResume={resumeInfo ? { id: resumeInfo.id, fileName: resumeInfo.fileName } : null}
          onClose={() => setShowUploadModal(false)}
          onFileSelected={(file) => void handleFileSelected(file)}
          onRemoveResume={handleRemoveResume}
        />
      )}

      {showActivityModal && (
        <AddActivityModal
          studentId={selectedStudent.id}
          activities={activities}
          onClose={() => setShowActivityModal(false)}
          onAdded={(activity) => {
            setActivities((prev) => [...prev, activity]);
            pushSystemNote(`"${activity.title}" added to your profile · ${activity.type}`);
          }}
          onRemoved={(activityId) => {
            const removed = activities.find((a) => a.id === activityId);
            setActivities((prev) => prev.filter((a) => a.id !== activityId));
            if (removed) pushSystemNote(`"${removed.title}" removed from your profile`);
          }}
        />
      )}
    </div>
  );
}
