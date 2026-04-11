import type {
  AnalyzeParams,
  AnalyzeResponse,
  SearchResponse,
} from './types';

// In dev with the Vite proxy, hit /api/* which proxies to http://localhost:8000.
// In prod, set VITE_API_BASE_URL to the deployed backend URL.
const API_BASE =
  (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/+$/, '') || '/api';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) },
    ...init,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body?.detail || JSON.stringify(body);
    } catch {
      /* noop */
    }
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

export class ApiError extends Error {
  status: number;
  detail: string;
  constructor(status: number, detail: string) {
    super(`[${status}] ${detail}`);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }
}

export function searchPapers(query: string, signal?: AbortSignal): Promise<SearchResponse> {
  const url = `/search?q=${encodeURIComponent(query)}`;
  return request<SearchResponse>(url, { signal });
}

export function analyzePaper(
  params: AnalyzeParams,
  signal?: AbortSignal,
): Promise<AnalyzeResponse> {
  return request<AnalyzeResponse>('/analyze', {
    method: 'POST',
    body: JSON.stringify(params),
    signal,
  });
}

export function healthCheck(signal?: AbortSignal): Promise<{ status: string }> {
  return request('/health', { signal });
}
