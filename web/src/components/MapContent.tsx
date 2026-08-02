"use client";

/**
 * MapContent — the actual Leaflet map.
 *
 * Loaded only via dynamic import (ssr: false) from RiskMap.tsx because
 * Leaflet reads `window` at import time and crashes during server-side rendering.
 *
 * Sprint 2 addition: optionally renders the FEMA flood zone polygon (GeoJSON)
 * returned by GET /flood. The polygon is styled by tier:
 *   High     → red fill
 *   Moderate → amber fill
 *   Low      → green fill
 *
 * MapUpdater keeps the viewport centred on the current pin without remounting
 * the entire MapContainer when the user searches a new address.
 */

import { useEffect } from "react";
import {
  GeoJSON,
  MapContainer,
  Marker,
  Popup,
  TileLayer,
  useMap,
} from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

// Leaflet's bundled icon paths break with most bundlers; point to the CDN copy.
const PIN_ICON = L.icon({
  iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  iconRetinaUrl:
    "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
  shadowSize: [41, 41],
});

const TIER_STYLES: Record<string, { color: string; fillColor: string }> = {
  High: { color: "#dc2626", fillColor: "#fca5a5" },      // red-600 / red-300
  Moderate: { color: "#d97706", fillColor: "#fcd34d" },  // amber-600 / amber-300
  Low: { color: "#16a34a", fillColor: "#86efac" },       // green-600 / green-300
};

function MapUpdater({ lat, lon }: { lat: number; lon: number }) {
  const map = useMap();
  useEffect(() => {
    map.setView([lat, lon], 15);
  }, [lat, lon, map]);
  return null;
}

interface Props {
  lat: number;
  lon: number;
  address: string;
  floodGeometry?: object | null;
  floodTier?: string | null;
  floodZoneCode?: string | null;
}

export default function MapContent({
  lat,
  lon,
  address,
  floodGeometry,
  floodTier,
  floodZoneCode,
}: Props) {
  const tierStyle = floodTier ? (TIER_STYLES[floodTier] ?? TIER_STYLES.Low) : null;

  // Build a FeatureCollection so react-leaflet's GeoJSON layer accepts it
  const geoJsonData =
    floodGeometry && tierStyle
      ? {
          type: "FeatureCollection" as const,
          features: [
            {
              type: "Feature" as const,
              properties: { zone: floodZoneCode },
              geometry: floodGeometry,
            },
          ],
        }
      : null;

  return (
    <MapContainer
      center={[lat, lon]}
      zoom={15}
      scrollWheelZoom={true}
      style={{ height: "100%", width: "100%" }}
    >
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap</a> contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />

      {/* Flood zone polygon — rendered below the pin so pin stays clickable */}
      {geoJsonData && tierStyle && (
        <GeoJSON
          key={`${lat},${lon}`}
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          data={geoJsonData as any}
          style={{
            color: tierStyle.color,
            fillColor: tierStyle.fillColor,
            fillOpacity: 0.25,
            weight: 2,
          }}
        />
      )}

      <Marker position={[lat, lon]} icon={PIN_ICON}>
        <Popup>{address}</Popup>
      </Marker>
      <MapUpdater lat={lat} lon={lon} />
    </MapContainer>
  );
}
