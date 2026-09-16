import type { ConsultationSummary } from "../api/consultation";

/**
 * Composes the message the assistant sends after a consultation report or Expo
 * poster finishes generating.
 *
 * The report endpoints return binary, so everything the model wrote for the
 * consultation -- the executive summary, the coach message, the first roadmap
 * step -- previously reached the student only if they opened the downloaded
 * file. The app just said "check your downloads". This surfaces the same
 * content in the conversation, which is where the student already is.
 *
 * It costs no extra model time: build_consultation_data is cached server-side
 * on a fingerprint of its inputs, so the summary request that follows a
 * download is a cache hit on work the download already paid for.
 */

const LOW_CONFIDENCE = "Limited evidence";

export function buildGeneratedBriefing(
  mode: "report" | "poster",
  summary: ConsultationSummary,
): string {
  const label = mode === "report" ? "consultation report" : "Expo poster";
  const sections: string[] = [];

  sections.push(
    `Your ${label} for ${summary.job_role_title} is ready — it's in your downloads. ` +
      `Here's what it says.`,
  );

  if (summary.executive_summary) sections.push(summary.executive_summary);

  if (summary.next_step) {
    sections.push(`Your first step (${summary.next_step.timeframe}):\n  • ${summary.next_step.actions}`);
  }

  if (summary.recommended_direction) {
    sections.push(`Direction that fits your evidence: ${summary.recommended_direction}`);
  }

  // The confidence bands are the report's own statement of how much evidence
  // each score rests on. Surfacing only the weak ones tells the student where
  // adding evidence would move the number most -- and keeps the report from
  // reading more authoritative than its inputs justify.
  const weak = Object.entries(summary.confidence)
    .filter(([, band]) => band === LOW_CONFIDENCE)
    .map(([category]) => category);
  if (weak.length > 0) {
    sections.push(
      `Worth knowing: ${weak.join(" and ")} ${weak.length === 1 ? "rests" : "rest"} on limited evidence, ` +
        `so ${weak.length === 1 ? "that score" : "those scores"} will move most as you add to your profile.`,
    );
  }

  if (summary.resume_note) sections.push(`About your resume score: ${summary.resume_note}`);

  if (summary.coach_message) sections.push(summary.coach_message);

  return sections.join("\n\n");
}
