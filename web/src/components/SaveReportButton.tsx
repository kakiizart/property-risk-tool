"use client";

import { useState } from "react";

import { ApiError, saveReport } from "@/lib/api";
import { useAuth } from "@/lib/auth";

/**
 * "Save report" action, shown only to signed-in users. Sends the address; the
 * server re-runs the pipeline and stores an authentic snapshot. Calls `onSaved`
 * so the parent can refresh the saved-reports list.
 */
export default function SaveReportButton({
  address,
  onSaved,
}: {
  address: string;
  onSaved?: () => void;
}) {
  const { user, accessToken } = useAuth();
  const [status, setStatus] = useState<"idle" | "saving" | "saved">("idle");
  const [error, setError] = useState<string | null>(null);

  if (!user || !accessToken) return null;

  async function handleSave() {
    if (!accessToken) return;
    setError(null);
    setStatus("saving");
    try {
      await saveReport(address, accessToken);
      setStatus("saved");
      onSaved?.();
    } catch (err) {
      setStatus("idle");
      if (err instanceof ApiError && err.status === 401) {
        setError("Your session expired — sign in again.");
      } else {
        setError(err instanceof Error ? err.message : "Could not save the report.");
      }
    }
  }

  return (
    <div className="flex items-center gap-3">
      <button
        type="button"
        onClick={handleSave}
        disabled={status === "saving" || status === "saved"}
        className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-800 hover:bg-slate-50 disabled:opacity-60"
      >
        {status === "saving" ? "Saving…" : status === "saved" ? "Saved ✓" : "Save report"}
      </button>
      {error && (
        <span role="alert" className="text-sm text-red-700">
          {error}
        </span>
      )}
    </div>
  );
}
