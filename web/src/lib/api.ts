/**
 * API client for the Property Risk backend.
 * Keeps all fetch logic out of presentation components.
 * Errors from non-2xx responses include the server's `detail` field when present.
 */

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface HealthResponse {
  status: string;
  service: string;
  environment: string;
}

export interface GeocodeResponse {
  lat: number;
  lon: number;
  tract_geoid: string;
  matched_address: string;
}

export interface FloodZoneResponse {
  zone_code: string;
  flood_tier: string;
  description: string;
  geometry: object;
}

export interface PerilScore {
  name: string;
  code: string;
  score: number | null;
  eal_usd: number | null;
  tier: string;
}

export interface NriResponse {
  tract_geoid: string;
  composite_score: number | null;
  eal_total_usd: number | null;
  perils: PerilScore[];
  source: string;
}

export interface CompositeContribution {
  code: string;
  name: string;
  score: number | null;
  weight: number;
  contribution: number | null; // score * normalised weight; sums to composite_score
}

export interface CompositeResult {
  composite_score: number | null;
  composite_tier: string;
  overall_tier: string; // more severe of composite_tier and flood_tier
  flood_tier: string;
  flood_is_sfha: boolean;
  weights: Record<string, number>;
  contributions: CompositeContribution[];
  methodology: string;
}

export interface ReportResponse {
  address: string;
  geocode: GeocodeResponse;
  flood: FloodZoneResponse | null;
  nri: NriResponse | null;
  composite: CompositeResult | null;
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

async function request<T>(
  method: "GET" | "POST",
  path: string,
  body?: unknown,
  timeoutMs = 10_000,
): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const res = await fetch(`${API_URL}${path}`, {
      method,
      signal: controller.signal,
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });

    if (!res.ok) {
      // Surface the server's error detail when available.
      let detail: string = res.statusText;
      try {
        const json = (await res.json()) as { detail?: string };
        if (json.detail) detail = json.detail;
      } catch {
        // ignore parse failure — use statusText
      }
      throw new Error(detail);
    }

    return (await res.json()) as T;
  } finally {
    clearTimeout(timer);
  }
}

// ---------------------------------------------------------------------------
// Public API calls
// ---------------------------------------------------------------------------

export function getHealth(): Promise<HealthResponse> {
  return request<HealthResponse>("GET", "/health");
}

/**
 * Geocode a US address to coordinates + census tract GEOID.
 * Throws with a human-readable message on failure (no match, service down, etc.).
 */
export function geocodeAddress(address: string): Promise<GeocodeResponse> {
  return request<GeocodeResponse>("POST", "/geocode", { address });
}

/**
 * Look up the FEMA flood zone for a lat/lon coordinate.
 * Returns zone code, flood tier, description, and GeoJSON polygon geometry.
 */
export function getFloodZone(lat: number, lon: number): Promise<FloodZoneResponse> {
  return request<FloodZoneResponse>("GET", `/flood?lat=${lat}&lon=${lon}`);
}

/**
 * Look up FEMA NRI per-peril scores for a census tract GEOID.
 * Returns composite score, EAL, and per-peril breakdown.
 * Throws with a descriptive message if the DB is not configured (503) or tract not found (404).
 */
export function getNriScores(tractGeoid: string): Promise<NriResponse> {
  return request<NriResponse>("GET", `/nri?tract_geoid=${tractGeoid}`);
}

/**
 * Full risk report for an address — geocode + flood + NRI + composite in one call.
 * `flood`, `nri`, and `composite` may be null if an upstream source is unavailable.
 */
export function getReport(address: string): Promise<ReportResponse> {
  return request<ReportResponse>("POST", "/report", { address });
}
