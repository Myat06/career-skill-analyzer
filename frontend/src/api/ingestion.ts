import { api } from "./client";

export interface IngestionRunOut {
  id: string;
  source_file: string;
  chunks_written: number;
  chunks_skipped: number;
  chunks_deleted: number;
  embedding_model_version: string;
  started_at: string;
  completed_at: string | null;
  status: string;
  notes: string | null;
}

export interface IngestionStatusOut {
  collection_counts: Record<string, number>;
  last_run_at: string | null;
}

export const ingestionApi = {
  run: (sources?: string[]) => api.post<IngestionRunOut[]>("/ingestion/run", { sources: sources ?? null }),
  runs: () => api.get<IngestionRunOut[]>("/ingestion/runs"),
  status: () => api.get<IngestionStatusOut>("/ingestion/status"),
};
