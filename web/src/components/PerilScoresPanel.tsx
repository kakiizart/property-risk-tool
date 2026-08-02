"use client";

/**
 * PerilScoresPanel — displays FEMA NRI per-peril risk scores and EAL.
 *
 * Shows a compact row per peril: name, score bar (0–100), tier badge, and
 * estimated annual loss. Scores come directly from FEMA NRI — we display
 * them as-is with full source attribution so the output is traceable.
 *
 * Tier colours match FloodZonePanel for visual consistency:
 *   High     → red
 *   Moderate → amber
 *   Low      → green
 *   Unknown  → slate (no data for this tract)
 */

import type { NriResponse } from "@/lib/api";

const TIER_BAR_COLOR: Record<string, string> = {
  High: "bg-red-500",
  Moderate: "bg-amber-500",
  Low: "bg-green-500",
  Unknown: "bg-slate-300",
};

const TIER_TEXT_COLOR: Record<string, string> = {
  High: "text-red-700",
  Moderate: "text-amber-700",
  Low: "text-green-700",
  Unknown: "text-slate-400",
};

function formatUsd(value: number | null): string {
  if (value === null) return "—";
  if (value >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `$${(value / 1_000).toFixed(0)}K`;
  return `$${value.toFixed(0)}`;
}

interface Props {
  data: NriResponse;
  loading?: boolean;
}

export default function PerilScoresPanel({ data, loading = false }: Props) {
  if (loading) {
    return (
      <div className="animate-pulse space-y-2 rounded-md border border-slate-200 bg-slate-50 px-4 py-3">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="h-4 rounded bg-slate-200" />
        ))}
      </div>
    );
  }

  return (
    <div className="rounded-md border border-slate-200 bg-white px-4 py-3 text-sm shadow-sm">
      {/* Header */}
      <div className="flex items-baseline justify-between">
        <span className="text-xs font-medium uppercase tracking-wide text-slate-400">
          Multi-Peril Risk Scores
        </span>
        {data.composite_score !== null && (
          <span className="text-xs text-slate-500">
            Composite:{" "}
            <span className="font-semibold text-slate-900">
              {data.composite_score.toFixed(1)} / 100
            </span>
          </span>
        )}
      </div>

      {data.eal_total_usd !== null && (
        <p className="mt-1 text-slate-600">
          Total Expected Annual Loss:{" "}
          <span className="font-semibold text-slate-900">
            {formatUsd(data.eal_total_usd)}
          </span>
          <span className="text-slate-400"> / year</span>
        </p>
      )}

      {/* Per-peril rows */}
      <div className="mt-3 space-y-2">
        {data.perils.map((peril) => (
          <div key={peril.code}>
            <div className="flex items-center justify-between">
              <span className="w-36 shrink-0 text-slate-700">{peril.name}</span>
              {/* Score bar */}
              <div className="mx-3 flex-1">
                <div className="h-2 overflow-hidden rounded-full bg-slate-100">
                  <div
                    className={`h-full rounded-full transition-all ${TIER_BAR_COLOR[peril.tier] ?? "bg-slate-300"}`}
                    style={{ width: `${peril.score ?? 0}%` }}
                  />
                </div>
              </div>
              <span
                className={`w-20 shrink-0 text-right text-xs font-medium ${TIER_TEXT_COLOR[peril.tier] ?? "text-slate-400"}`}
              >
                {peril.score !== null ? `${peril.score.toFixed(1)}` : "No data"}
              </span>
              <span className="ml-3 w-16 shrink-0 text-right text-xs text-slate-500">
                {formatUsd(peril.eal_usd)}
              </span>
            </div>
          </div>
        ))}
      </div>

      {/* Methodology link */}
      <p className="mt-3 text-xs text-slate-400">
        Scores 0–100 from{" "}
        <a
          href="https://hazards.fema.gov/nri/"
          target="_blank"
          rel="noreferrer"
          className="underline hover:text-slate-600"
        >
          FEMA National Risk Index
        </a>
        {" · EAL = Expected Annual Loss · "}
        <a href="/docs/methodology" className="underline hover:text-slate-600">
          Methodology
        </a>
      </p>
    </div>
  );
}
