"use client";

/**
 * FloodZonePanel — displays the FEMA flood zone result.
 *
 * Shows zone code, tier badge, and description. The tier badge uses colour
 * to reinforce the risk level (red = High, amber = Moderate, green = Low)
 * without relying on colour alone — the tier label is always present.
 */

import type { FloodZoneResponse } from "@/lib/api";

const TIER_STYLES: Record<string, string> = {
  High: "bg-red-100 text-red-800 border border-red-200",
  Moderate: "bg-amber-100 text-amber-800 border border-amber-200",
  Low: "bg-green-100 text-green-800 border border-green-200",
};

interface Props {
  data: FloodZoneResponse;
  loading?: boolean;
}

export default function FloodZonePanel({ data, loading = false }: Props) {
  if (loading) {
    return (
      <div className="animate-pulse rounded-md border border-slate-200 bg-slate-50 px-4 py-3">
        <div className="h-4 w-1/3 rounded bg-slate-200" />
        <div className="mt-2 h-3 w-2/3 rounded bg-slate-200" />
      </div>
    );
  }

  const tierStyle =
    TIER_STYLES[data.flood_tier] ?? "bg-slate-100 text-slate-700 border border-slate-200";

  return (
    <div className="rounded-md border border-slate-200 bg-white px-4 py-3 text-sm shadow-sm">
      {/* Header row */}
      <div className="flex items-center justify-between gap-3">
        <div>
          <span className="text-xs font-medium uppercase tracking-wide text-slate-400">
            Flood Zone
          </span>
          <p className="mt-0.5 text-lg font-semibold text-slate-900">
            Zone {data.zone_code}
          </p>
        </div>
        <span
          className={`inline-flex shrink-0 items-center rounded-full px-3 py-1 text-xs font-semibold ${tierStyle}`}
        >
          {data.flood_tier} Risk
        </span>
      </div>

      {/* Description */}
      <p className="mt-2 text-slate-600">{data.description}</p>

      {/* Source attribution */}
      <p className="mt-3 text-xs text-slate-400">
        Source:{" "}
        <a
          href="https://www.fema.gov/flood-maps/national-flood-hazard-layer"
          target="_blank"
          rel="noreferrer"
          className="underline hover:text-slate-600"
        >
          FEMA National Flood Hazard Layer
        </a>
        {" · "}
        <a
          href="https://msc.fema.gov/portal/search"
          target="_blank"
          rel="noreferrer"
          className="underline hover:text-slate-600"
        >
          Verify on FEMA MSC
        </a>
      </p>
    </div>
  );
}
