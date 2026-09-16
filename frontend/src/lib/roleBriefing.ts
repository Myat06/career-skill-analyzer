import type { SkillGapResponse, UnitCoverage } from "../types";

/**
 * Composes the message the assistant sends right after a target role is chosen.
 *
 * Everything here comes from the skill-gap response the app has *already*
 * fetched: `runSkillGap` generates a citation-checked narrative (strengths,
 * weaknesses, suggestions) as part of that call, and the UI previously
 * discarded all of it in favour of a one-line "Target role set to X — 73%
 * match". So this adds no latency and no extra model call -- it just stops
 * throwing away work that was already paid for, and every claim it prints has
 * already passed the citation check in app/scoring/narrative.py.
 *
 * The tone tracks the actual match: a 73% fit is genuinely encouraging, but a
 * 25% fit congratulated as a great choice would be flattery, and would teach
 * students to distrust the number sitting right next to it.
 */

interface Band {
  /** Inclusive lower bound of the match percentage. */
  min: number;
  verdict: string;
}

const BANDS: Band[] = [
  { min: 70, verdict: "That's a strong fit — you're already most of the way there." },
  { min: 50, verdict: "That's a solid fit, with a clear path to close the rest." },
  { min: 30, verdict: "That's a stretch right now, but a realistic one to work toward." },
  { min: 0, verdict: "That's an ambitious choice — it would mean building most of these competencies from scratch." },
];

function verdictFor(matchPercentage: number): string {
  return (BANDS.find((b) => matchPercentage >= b.min) ?? BANDS[BANDS.length - 1]).verdict;
}

// Real Markdown list syntax ("- item"), not a literal "•" character: a plain
// "•"-prefixed line is just paragraph text to the renderer, and CommonMark
// collapses consecutive single-newline lines within a paragraph into one
// run-on sentence -- which is why this used to render as "• point one • point
// two" all on one line instead of an actual bulleted list.
function bullets(points: { text: string }[], limit: number): string {
  return points
    .slice(0, limit)
    .map((p) => `- ${p.text}`)
    .join("\n");
}

function unitStatusLabel(coverageFraction: number): string {
  return coverageFraction > 0 ? `Partial (${Math.round(coverageFraction * 100)}%)` : "Missing";
}

// Mirrors the live chat's own table-vs-list rule: a table earns its place only
// when each item has 2+ attributes worth comparing side by side (here: status
// and what's missing). Built from the structured gap units rather than the
// narrative's free-text weaknesses, since those don't carry a per-unit
// breakdown the frontend can safely split into columns.
function gapTable(units: UnitCoverage[], limit: number): string {
  const rows = units
    .slice(0, limit)
    .map((u) => {
      const title = u.unit_title || u.unit_code;
      const missing = u.unmatched_elements.slice(0, 3).join("; ") || "—";
      return `| ${title} | ${unitStatusLabel(u.coverage_fraction)} | ${missing} |`;
    })
    .join("\n");
  return `| Competency | Status | What's missing |\n|---|---|---|\n${rows}`;
}

function joinTitles(titles: string[], limit: number): string {
  const shown = titles.slice(0, limit);
  const rest = titles.length - shown.length;
  const list = shown.join(", ");
  return rest > 0 ? `${list}, and ${rest} more` : list;
}

export function buildRoleBriefing(result: SkillGapResponse): string {
  const { job_role, match_percentage, matched_units, partial_units, missing_units, narrative } = result;
  const totalUnits = matched_units.length + partial_units.length + missing_units.length;
  const sections: string[] = [];

  sections.push(
    `${job_role.role_title} — ${match_percentage.toFixed(0)}% match\n${verdictFor(match_percentage)}`,
  );

  if (matched_units.length > 0) {
    const titles = joinTitles(
      matched_units.map((u) => u.unit_title || u.unit_code),
      3,
    );
    sections.push(
      `Based on your completed courses, logged activities and resume, you already cover ` +
        `${matched_units.length} of the ${totalUnits} competencies this role requires — including ${titles}.`,
    );
  }

  // narrative is null when the model was unreachable, and its claim lists can
  // be empty when claims were dropped for failing the citation check. Either
  // way the deterministic sections above still stand on their own.
  const strengths = narrative?.strengths ?? [];
  if (strengths.length > 0) {
    sections.push(`What's working in your favour:\n${bullets(strengths, 3)}`);
  }

  const gapUnits = [...partial_units, ...missing_units];
  const gapCount = gapUnits.length;
  const weaknesses = narrative?.weaknesses ?? [];
  if (weaknesses.length > 0) {
    sections.push(
      gapUnits.length >= 2
        ? `Where you'd need to grow:\n${gapTable(gapUnits, 5)}`
        : `Where you'd need to grow:\n${bullets(weaknesses, 3)}`,
    );
  } else if (gapCount > 0) {
    const titles = joinTitles(
      gapUnits.map((u) => u.unit_title || u.unit_code),
      3,
    );
    sections.push(`Still to build: ${titles}.`);
  }

  // Recommended courses can legitimately be empty now that retrieval applies a
  // relevance floor (COURSE_MATCH_MIN_SIMILARITY) -- saying so plainly is the
  // point of that floor, and beats naming an unrelated course.
  // Course code omitted -- current curriculum data is test fixture data, not the
  // real catalog, so codes aren't safe to show a student yet. Restore
  // `${c.course_name} (${c.course_code})` once real curriculum data lands.
  const courseNames = [...new Set(result.recommended_courses.map((c) => c.course_name))];
  if (courseNames.length > 0) {
    sections.push(`Courses in your catalogue that would help close these gaps:\n${
      courseNames.slice(0, 4).map((c) => `- ${c}`).join("\n")
    }`);
  } else if (gapCount > 0) {
    sections.push(
      "No course in your catalogue covers these gaps closely enough for me to recommend one — " +
        "these are better closed through projects, internships or certifications.",
    );
  }

  sections.push(
    gapCount > 0
      ? "Ask me how to close any of these gaps, or generate your consultation report and Expo poster when you're ready."
      : "Ask me anything about this role, or generate your consultation report and Expo poster when you're ready.",
  );

  return sections.join("\n\n");
}
