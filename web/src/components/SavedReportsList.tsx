"use client";

import { useCallback, useEffect, useState } from "react";

import {
  ApiError,
  deleteReport,
  getSavedReport,
  listReports,
  type ReportResponse,
  type SavedReportSummary,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";

const TIER_STYLES: Record<string, string> = {
  High: "bg-red-100 text-red-800",
  Moderate: "bg-amber-100 text-amber-800",
  Low: "bg-emerald-100 text-emerald-800",
};

function TierBadge({ tier }: { tier: string | null }) {
  if (!tier) return null;
  const cls = TIER_STYLES[tier] ?? "bg-slate-100 text-slate-700";
  return (
    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${cls}`}>{tier}</span>
  );
}

/**
 * The signed-in user's saved reports: list with view + delete. Renders nothing
 * when signed out. Reloads whenever `refreshSignal` changes (e.g. after a save).
 */
export default function SavedReportsList({
  refreshSignal,
  onOpen,
}: {
  refreshSignal: number;
  onOpen: (report: ReportResponse) => void;
}) {
  const { user, accessToken } = useAuth();
  const [items, setItems] = useState<SavedReportSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!accessToken) return;
    setError(null);
    try {
      setItems(await listReports(accessToken));
    } catch (err) {
      setItems([]);
      setError(errorMessage(err, "Could not load your saved reports."));
    }
  }, [accessToken]);

  // Drop the previous account's data immediately when the signed-in identity
  // changes, so one user's saved reports can never flash under another user's
  // session while the new list loads. Keyed on the user id (not the whole user
  // object) so a token refresh reloads without clearing to a skeleton.
  useEffect(() => {
    setItems(null);
    setError(null);
  }, [user?.id]);

  useEffect(() => {
    if (user && accessToken) void load();
  }, [user, accessToken, refreshSignal, load]);

  if (!user) return null;

  async function handleOpen(id: string) {
    if (!accessToken) return;
    setBusyId(id);
    setError(null);
    try {
      const detail = await getSavedReport(id, accessToken);
      onOpen(detail.result);
    } catch (err) {
      setError(errorMessage(err, "Could not open that report."));
    } finally {
      setBusyId(null);
    }
  }

  async function handleDelete(id: string) {
    if (!accessToken) return;
    setBusyId(id);
    setError(null);
    try {
      await deleteReport(id, accessToken);
      await load();
    } catch (err) {
      setError(errorMessage(err, "Could not delete that report."));
    } finally {
      setBusyId(null);
    }
  }

  return (
    <section className="rounded-md border border-slate-200 bg-white p-4" aria-label="Saved reports">
      <h2 className="text-sm font-semibold text-slate-900">Your saved reports</h2>

      {error && (
        <p role="alert" className="mt-2 text-sm text-red-700">
          {error}
        </p>
      )}

      {items === null ? (
        <div className="mt-3 space-y-2" aria-label="Loading saved reports">
          <div className="h-10 animate-pulse rounded-md bg-slate-100" />
          <div className="h-10 animate-pulse rounded-md bg-slate-100" />
        </div>
      ) : items.length === 0 ? (
        <p className="mt-2 text-sm text-slate-500">
          No saved reports yet. Run a report above and choose “Save report”.
        </p>
      ) : (
        <ul className="mt-3 divide-y divide-slate-100">
          {items.map((r) => (
            <li key={r.id} className="flex items-center justify-between gap-3 py-2">
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-slate-900">{r.address}</p>
                <p className="text-xs text-slate-500">
                  {new Date(r.created_at).toLocaleDateString()}
                </p>
              </div>
              <div className="flex shrink-0 items-center gap-3">
                <TierBadge tier={r.overall_tier} />
                <button
                  type="button"
                  onClick={() => handleOpen(r.id)}
                  disabled={busyId === r.id}
                  className="text-sm font-medium text-slate-700 hover:text-slate-900 disabled:opacity-50"
                >
                  View
                </button>
                <button
                  type="button"
                  onClick={() => handleDelete(r.id)}
                  disabled={busyId === r.id}
                  className="text-sm font-medium text-red-600 hover:text-red-800 disabled:opacity-50"
                >
                  Delete
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function errorMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError && err.status === 401) {
    return "Your session expired — sign in again.";
  }
  return err instanceof Error ? err.message : fallback;
}
