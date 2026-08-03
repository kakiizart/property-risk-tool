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

// --- Saved reports (auth-required) ---

export interface SavedReportSummary {
  id: string;
  address: string;
  overall_tier: string | null;
  created_at: string; // ISO 8601
}

export interface SavedReportDetail {
  id: string;
  address: string;
  created_at: string; // ISO 8601
  updated_at: string; // ISO 8601
  result: ReportResponse; // full snapshot, same shape as a live report
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

/** Error carrying the HTTP status, so callers can special-case 401/403 etc. */
export class ApiError extends Error {
  readonly status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(
  method: "GET" | "POST" | "DELETE",
  path: string,
  body?: unknown,
  timeoutMs = 10_000,
  token?: string,
): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  const headers: Record<string, string> = {};
  if (body) headers["Content-Type"] = "application/json";
  if (token) headers["Authorization"] = `Bearer ${token}`;

  try {
    const res = await fetch(`${API_URL}${path}`, {
      method,
      signal: controller.signal,
      headers,
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
      throw new ApiError(res.status, detail);
    }

    if (res.status === 204) return undefined as T; // no content (e.g. DELETE)
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
 * Client timeout for the aggregate /report call.
 *
 * Unlike the per-endpoint calls, /report runs geocode -> (flood + NRI) on the
 * server, so its worst case is the geocode budget *plus* the flood/NRI budget,
 * not a single endpoint's. The backend allows an 8s timeout with one retry per
 * external service, i.e. geocode up to ~16s followed by flood/NRI (concurrent)
 * up to ~16s. Give the browser room to outlast that so a slow-but-valid request
 * isn't aborted client-side; the typical response is 1-3s.
 */
const REPORT_TIMEOUT_MS = 35_000;

/**
 * Full risk report for an address — geocode + flood + NRI + composite in one call.
 * `flood`, `nri`, and `composite` may be null if an upstream source is unavailable.
 */
export function getReport(address: string): Promise<ReportResponse> {
  return request<ReportResponse>("POST", "/report", { address }, REPORT_TIMEOUT_MS);
}

// ---------------------------------------------------------------------------
// Saved reports — all require a Supabase access token
// ---------------------------------------------------------------------------

/**
 * Build and save a report for the current user.
 * The server re-runs the pipeline, so this shares /report's latency budget.
 */
export function saveReport(address: string, token: string): Promise<SavedReportDetail> {
  return request<SavedReportDetail>("POST", "/reports", { address }, REPORT_TIMEOUT_MS, token);
}

/** List the current user's saved reports (newest first). */
export function listReports(token: string): Promise<SavedReportSummary[]> {
  return request<SavedReportSummary[]>("GET", "/reports", undefined, 10_000, token);
}

/** Fetch one saved report (with its full snapshot) by id. */
export function getSavedReport(id: string, token: string): Promise<SavedReportDetail> {
  return request<SavedReportDetail>("GET", `/reports/${id}`, undefined, 10_000, token);
}

/** Delete one saved report by id. */
export function deleteReport(id: string, token: string): Promise<void> {
  return request<void>("DELETE", `/reports/${id}`, undefined, 10_000, token);
}
