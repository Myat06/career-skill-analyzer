import { useEffect, useState } from "react";
import { ingestionApi, type IngestionRunOut, type IngestionStatusOut } from "../api/ingestion";

export default function IngestionAdmin() {
  const [status, setStatus] = useState<IngestionStatusOut | null>(null);
  const [runs, setRuns] = useState<IngestionRunOut[]>([]);
  const [running, setRunning] = useState(false);

  const refresh = () => {
    ingestionApi.status().then(setStatus);
    ingestionApi.runs().then(setRuns);
  };

  useEffect(refresh, []);

  const triggerRun = async () => {
    setRunning(true);
    try {
      await ingestionApi.run();
      refresh();
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-slate-900">Ingestion</h1>
        <button
          type="button"
          onClick={triggerRun}
          disabled={running}
          className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
        >
          {running ? "Synchronizing…" : "Synchronize now"}
        </button>
      </div>

      {status && (
        <div className="grid grid-cols-2 gap-4 md:w-1/2">
          <div className="rounded-lg border border-slate-200 bg-white p-4 text-center shadow-sm">
            <p className="text-2xl font-bold text-slate-900">{status.collection_counts.skkni_units ?? 0}</p>
            <p className="text-xs text-slate-500">SKKNI chunks</p>
          </div>
          <div className="rounded-lg border border-slate-200 bg-white p-4 text-center shadow-sm">
            <p className="text-2xl font-bold text-slate-900">{status.collection_counts.curriculum_courses ?? 0}</p>
            <p className="text-xs text-slate-500">Curriculum chunks</p>
          </div>
        </div>
      )}

      <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white shadow-sm">
        <table className="w-full min-w-150 text-left text-sm">
          <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-4 py-2">Source</th>
              <th className="px-4 py-2">Written</th>
              <th className="px-4 py-2">Skipped</th>
              <th className="px-4 py-2">Deleted</th>
              <th className="px-4 py-2">Status</th>
              <th className="px-4 py-2">Started</th>
            </tr>
          </thead>
          <tbody>
            {runs.map((run) => (
              <tr key={run.id} className="border-t border-slate-100">
                <td className="px-4 py-2">{run.source_file}</td>
                <td className="px-4 py-2">{run.chunks_written}</td>
                <td className="px-4 py-2">{run.chunks_skipped}</td>
                <td className="px-4 py-2">{run.chunks_deleted}</td>
                <td className="px-4 py-2">{run.status}</td>
                <td className="px-4 py-2 text-slate-400">{new Date(run.started_at).toLocaleString()}</td>
              </tr>
            ))}
            {runs.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-6 text-center text-slate-400">
                  No ingestion runs yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
