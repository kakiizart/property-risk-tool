"use client";

import { useState } from "react";
import AddressSearch from "@/components/AddressSearch";
import FloodZonePanel from "@/components/FloodZonePanel";
import PerilScoresPanel from "@/components/PerilScoresPanel";
import RiskMap from "@/components/RiskMap";
import RiskReportSummary from "@/components/RiskReportSummary";
import { getReport, type ReportResponse } from "@/lib/api";

export default function Home() {
  const [report, setReport] = useState<ReportResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSearch(address: string) {
    setError(null);
    setReport(null);
    setLoading(true);

    // One call: the API geocodes, looks up flood + NRI, and scores the composite.
    try {
      const result = await getReport(address);
      setReport(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not build the risk report.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="mx-auto max-w-3xl px-6 py-16">
      <h1 className="text-3xl font-semibold tracking-tight text-slate-900">
        Property Risk &amp; Hazard Exposure
      </h1>
      <p className="mt-3 text-slate-600">
        Enter a US address to get a transparent, source-traceable multi-peril
        risk profile built on FEMA National Risk Index and National Flood Hazard
        Layer data.
      </p>

      <div className="mt-8">
        <AddressSearch onSearch={handleSearch} />
      </div>

      {error && (
        <div
          role="alert"
          className="mt-4 rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700"
        >
          {error}
        </div>
      )}

      {loading && (
        <div className="mt-6 animate-pulse space-y-4" aria-label="Building risk report">
          <div className="h-28 rounded-lg bg-slate-100" />
          <div className="h-20 rounded-md bg-slate-100" />
          <div className="h-40 rounded-md bg-slate-100" />
        </div>
      )}

      {report && !loading && (
        <div className="mt-6 space-y-4">
          {/* Overall assessment (composite + flood callout) */}
          {report.composite && (
            <RiskReportSummary
              data={report.composite}
              matchedAddress={report.geocode.matched_address}
            />
          )}

          {/* Geocode result card */}
          <div className="rounded-md border border-slate-200 bg-slate-50 px-4 py-3 text-sm">
            <p className="font-medium text-slate-900">{report.geocode.matched_address}</p>
            <p className="mt-1 text-slate-500">
              {report.geocode.lat.toFixed(5)}, {report.geocode.lon.toFixed(5)}
              &ensp;·&ensp;Census tract&nbsp;
              <span className="font-mono">{report.geocode.tract_geoid}</span>
            </p>
          </div>

          {/* Flood zone */}
          {report.flood ? (
            <FloodZonePanel data={report.flood} />
          ) : (
            <div className="rounded-md border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-500">
              Flood zone data is currently unavailable for this location.
            </div>
          )}

          {/* NRI per-peril scores */}
          {report.nri ? (
            <PerilScoresPanel data={report.nri} />
          ) : (
            <div className="rounded-md border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-500">
              NRI risk scores are unavailable for this census tract.
            </div>
          )}

          {/* Map */}
          <RiskMap geocode={report.geocode} flood={report.flood} />
        </div>
      )}

      {!report && !error && !loading && (
        <p className="mt-8 text-sm text-slate-400">
          Enter a US address above to see its overall risk assessment, flood
          zone, and multi-peril profile.
        </p>
      )}
    </main>
  );
}
