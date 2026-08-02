/**
 * API client for the Property Risk backend.
 * Keeps all fetch logic out of presentation components.
 */

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface HealthResponse {
  status: string;
  service: string;
  environment: string;
}

async function getJson<T>(path: string, timeoutMs = 8000): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(`${API_URL}${path}`, { signal: controller.signal });
    if (!res.ok) {
      throw new Error(`Request to ${path} failed with ${res.status}`);
    }
    return (await res.json()) as T;
  } finally {
    clearTimeout(timer);
  }
}

export function getHealth(): Promise<HealthResponse> {
  return getJson<HealthResponse>("/health");
}
