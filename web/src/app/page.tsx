"use client";

import { useState } from "react";
import AddressSearch from "@/components/AddressSearch";
import FloodZonePanel from "@/components/FloodZonePanel";
import PerilScoresPanel from "@/components/PerilScoresPanel";
import RiskMap from "@/components/RiskMap";
import {
  geocodeAddress,
  getFloodZone,
  getNriScores,
  type FloodZoneResponse,
  type GeocodeResponse,
  type NriResponse,
} from "@/lib/api";

export default function Home() {
  const [geocode, setGeocode] = useState<GeocodeResponse | null>(null);
  const [flood, setFlood] = useState<FloodZoneResponse | null>(null);
  const [nri, setNri] = useState<NriResponse | null>(null);
  const [floodLoading, setFloodLoading] = useState(false);
  const [nriLoading, setNriLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSearch(address: string) {
    setError(null);
    setGeocode(null);
    setFlood(null);
    setNri(null);

    // Step 1 — geocode (blocking: we need lat/lon + GEOID for everything else)
    let geo: GeocodeResponse;
    try {
      geo = await geocodeAddress(address);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Geocoding failed.");
      return;
    }
    setGeocode(geo);

    // Steps 2 & 3 — flood zone + NRI scores run in parallel after geocode
    setFloodLoading(true);
    setNriLoading(true);

    const [floodResult, nriResult] = await Promise.allSettled([
      getFloodZone(geo.lat, geo.lon),
      getNriScores(geo.tract_geoid),
    ]);

    if (floodResult.status === "fulfilled") {
      setFlood(floodResult.value);
    } else {
      console.warn("Flood zone lookup failed:", floodResult.reason);
    }
    setFloodLoading(false);

    if (nriResult.status === "fulfilled") {
      setNri(nriResult.value);
    } else {
      // NRI 503 is expected when DATABASE_URL is not set (early dev / no Supabase yet)
      console.warn("NRI lookup failed:", nriResult.reason);
    }
    setNriLoading(false);
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

      {geocode && (
        <div className="mt-4 space-y-4">
          {/* Geocode result card */}
          <div className="rounded-md border border-slate-200 bg-slate-50 px-4 py-3 text-sm">
            <p className="font-medium text-slate-900">{geocode.matched_address}</p>
            <p className="mt-1 text-slate-500">
              {geocode.lat.toFixed(5)}, {geocode.lon.toFixed(5)}
              &ensp;·&ensp;Census tract&nbsp;
              <span className="font-mono">{geocode.tract_geoid}</span>
            </p>
          </div>

          {/* Flood zone panel */}
          {(floodLoading || flood) && (
            <FloodZonePanel
              data={flood ?? { zone_code: "…", flood_tier: "Low", description: "", geometry: {} }}
              loading={floodLoading}
            />
          )}

          {/* NRI per-peril panel */}
          {(nriLoading || nri) && (
            <PerilScoresPanel
              data={
                nri ?? {
                  tract_geoid: geocode.tract_geoid,
                  composite_score: null,
                  eal_total_usd: null,
                  perils: [],
                  source: "",
                }
              }
              loading={nriLoading}
            />
          )}

          {/* Leaflet map */}
          <RiskMap geocode={geocode} flood={flood} />
        </div>
      )}

      {!geocode && !error && (
        <p className="mt-8 text-sm text-slate-400">
          Enter a US address above to see its flood zone and multi-peril risk profile.
        </p>
      )}
    </main>
  );
}
