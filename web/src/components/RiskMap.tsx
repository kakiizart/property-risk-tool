"use client";

/**
 * RiskMap — Leaflet map wrapper for the risk result.
 *
 * Uses next/dynamic with ssr:false to load MapContent only on the client.
 * Leaflet cannot run during server-side rendering because it accesses `window`.
 * MapContent handles the map; this file owns container sizing and the loading
 * state shown while the Leaflet bundle is fetched.
 *
 * Sprint 2: passes flood zone geometry and tier to MapContent so the polygon
 * is drawn on the map in tier-appropriate colour.
 */

import dynamic from "next/dynamic";
import type { FloodZoneResponse, GeocodeResponse } from "@/lib/api";

const MapContent = dynamic(() => import("./MapContent"), {
  ssr: false,
  loading: () => (
    <div className="flex h-full items-center justify-center text-sm text-slate-500">
      Loading map…
    </div>
  ),
});

interface Props {
  geocode: GeocodeResponse;
  flood?: FloodZoneResponse | null;
}

export default function RiskMap({ geocode, flood }: Props) {
  return (
    <div className="mt-6 h-96 w-full overflow-hidden rounded-lg border border-slate-200 shadow-sm">
      <MapContent
        lat={geocode.lat}
        lon={geocode.lon}
        address={geocode.matched_address}
        floodGeometry={
          flood?.geometry && Object.keys(flood.geometry).length > 0
            ? flood.geometry
            : null
        }
        floodTier={flood?.flood_tier ?? null}
        floodZoneCode={flood?.zone_code ?? null}
      />
    </div>
  );
}
