"use client";

/**
 * RiskReportSummary — the top-of-report overall assessment.
 *
 * Surfaces the documented composite (a weighted average of the region-relevant
 * NRI perils) alongside its per-peril contributions, and calls out FEMA flood
 * status separately — flood is never blended into the composite (see
 * docs/methodology.md). Overall tier is the more severe of the composite tier
 * and the flood tier, so Special-Flood-Hazard-Area status is never hidden.
 */

import type { CompositeResult } from "@/lib/api";

const TIER_BADGE: Record<string, string> = {
  High: "bg-red-100 text-red-800 border-red-200",
  Moderate: "bg-amber-100 text-amber-800 border-amber-200",
  Low: "bg-green-100 text-green-800 border-green-200",
  Unknown: "bg-slate-100 text-slate-700 border-slate-200",
};

const TIER_BAR: Record<string, string> = {
  High: "bg-red-500",
  Moderate: "bg-amber-500",
  Low: "bg-green-500",
  Unknown: "bg-slate-300",
};

function tierForScore(score: number | null): string {
  if (score === null) return "Unknown";
  if (score >= 50) return "High";
  if (score >= 25) return "Moderate";
  return "Low";
}

interface Props {
  data: CompositeResult;
  matchedAddress: string;
}

export default function RiskReportSummary({ data, matchedAddress }: Props) {
  const overallBadge = TIER_BADGE[data.overall_tier] ?? TIER_BADGE.Unknown;

  const contributions = [...data.contributions].sort(
    (a, b) => (b.contribution ?? 0) - (a.contribution ?? 0),
  );
  const maxContribution = Math.max(
    1,
    ...contributions.map((c) => c.contribution ?? 0),
  );

  return (
    <div className="rounded-lg border border-slate-200 bg-white px-5 py-4 shadow-sm">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <span className="text-xs font-medium uppercase tracking-wide text-slate-400">
            Overall Risk Assessment
          </span>
          <p className="mt-0.5 text-sm text-slate-600">{matchedAddress}</p>
        </div>
        <span
          className={`inline-flex shrink-0 items-center rounded-full border px-4 py-1.5 text-sm font-semibold ${overallBadge}`}
        >
          {data.overall_tier} Risk
        </span>
      </div>

      {/* Composite score */}
      <div className="mt-4 flex items-baseline gap-2">
        <span className="text-3xl font-semibold text-slate-900">
          {data.composite_score !== null ? data.composite_score.toFixed(1) : "—"}
        </span>
        <span className="text-sm text-slate-400">
          / 100 regional composite&ensp;·&ensp;{data.composite_tier}
        </span>
      </div>

      {/* Flood — called out separately, never blended */}
      {data.flood_is_sfha ? (
        <div
          role="alert"
          className="mt-3 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800"
        >
          ⚠ In a FEMA Special Flood Hazard Area (flood tier{" "}
          <span className="font-semibold">{data.flood_tier}</span>). Flood
          insurance is typically required for federally backed mortgages.
        </div>
      ) : (
        <p className="mt-2 text-xs text-slate-500">
          Flood tier (carried separately, not blended into the composite):{" "}
          <span className="font-medium text-slate-700">{data.flood_tier}</span>
        </p>
      )}

      {/* Contribution breakdown */}
      <div className="mt-4">
        <p className="text-xs font-medium uppercase tracking-wide text-slate-400">
          What drives the composite
        </p>
        <div className="mt-2 space-y-1.5">
          {contributions.map((c) => (
            <div key={c.code} className="flex items-center gap-3 text-sm">
              <span className="w-36 shrink-0 text-slate-700">{c.name}</span>
              <div className="flex-1">
                <div className="h-2 overflow-hidden rounded-full bg-slate-100">
                  <div
                    className={`h-full rounded-full transition-all ${TIER_BAR[tierForScore(c.score)]}`}
                    style={{
                      width: `${((c.contribution ?? 0) / maxContribution) * 100}%`,
                    }}
                  />
                </div>
              </div>
              <span className="w-14 shrink-0 text-right text-xs text-slate-400">
                wt {(c.weight * 100).toFixed(0)}%
              </span>
              <span className="w-12 shrink-0 text-right text-xs font-medium text-slate-700">
                {c.contribution !== null ? c.contribution.toFixed(1) : "—"}
              </span>
            </div>
          ))}
        </div>
      </div>

      <p className="mt-3 text-xs text-slate-400">{data.methodology}</p>
    </div>
  );
}
