export interface Student {
  id: string;
  student_no: string;
  full_name: string;
  program: string;
  cohort_year: number;
  email: string;
}

export interface EnrollmentOut {
  id: string;
  course_code: string;
  grade: string | null;
  grade_point: number | null;
  semester_taken: number;
  status: string;
}

export type ActivityType =
  | "project"
  | "certification"
  | "internship"
  | "organization"
  | "competition"
  | "volunteer";

export interface ActivityOut {
  id: string;
  type: ActivityType;
  title: string;
  description: string;
  issuer: string | null;
  start_date: string | null;
  end_date: string | null;
  skills_tags: string[];
  evidence_url: string | null;
  created_at: string;
}

export interface ActivityIn {
  type: ActivityType;
  title: string;
  description: string;
  issuer?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  skills_tags?: string[];
  evidence_url?: string | null;
}

export interface StudentProfile {
  student: Student;
  completed_courses: EnrollmentOut[];
  in_progress_courses: EnrollmentOut[];
  activities: ActivityOut[];
  gpa: number | null;
}

export interface JobRole {
  id: string;
  role_title: string;
  role_slug: string;
  source: string;
  sector: string | null;
  description: string | null;
  required_unit_codes: string[];
  is_curated: boolean;
}

export interface JobRoleResolveResult {
  matched_job_role: JobRole | null;
  confidence: number;
  low_confidence: boolean;
  candidate_unit_codes: string[];
}

export interface UnitCoverage {
  unit_code: string;
  unit_title: string;
  coverage_fraction: number;
  matched_elements: string[];
  unmatched_elements: string[];
}

export interface RecommendedCourse {
  course_code: string;
  course_name: string;
  for_unit_code: string;
  match_reason: string;
}

export interface NarrativePoint {
  text: string;
  citations: string[];
}

export interface Narrative {
  strengths: NarrativePoint[];
  weaknesses: NarrativePoint[];
  improvement_suggestions: NarrativePoint[];
  citations_valid: boolean;
  repair_attempted: boolean;
}

export interface SkillGapResponse {
  analysis_id: string;
  job_role: JobRole;
  match_percentage: number;
  matched_units: UnitCoverage[];
  partial_units: UnitCoverage[];
  missing_units: UnitCoverage[];
  recommended_courses: RecommendedCourse[];
  narrative: Narrative | null;
  narrative_status: "ok" | "unavailable" | "degraded";
  embedding_model_version: string;
}

export interface SkillGapSummary {
  id: string;
  job_role_id: string;
  match_percentage: number;
  created_at: string;
}

export interface ResumeOut {
  id: string;
  student_id: string;
  source: "uploaded" | "auto_generated";
  original_filename: string | null;
  extracted_text: string;
  parsed_sections: Record<string, unknown>;
  created_at: string;
}

export interface ResumeSuggestion {
  text: string;
  origin: "rule-based" | "ai-suggested";
}

export interface RubricCategoryScore {
  key: string;
  label: string;
  score: number;
  feedback: string;
  quote: string | null;
}

export interface ResumeScoreOut {
  resume_id: string;
  job_role_id: string | null;
  rubric_categories: RubricCategoryScore[];
  keyword_alignment_score: number;
  overall_score: number;
  suggestions: ResumeSuggestion[];
  note: string | null;
}
