import { getInitData } from '../max/bridge';
import { ApiError } from './errors';
import { mockGet } from './mocks';

const USE_MOCKS = import.meta.env.VITE_USE_MOCKS === '1';

export async function apiGet<T>(path: string): Promise<T> {
  if (USE_MOCKS) return mockGet<T>(path);

  const response = await fetch(`/api${path}`, { headers: { 'X-Max-Init-Data': getInitData() } });
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as { code?: string; detail?: string };
    throw new ApiError(response.status, body.code ?? '', body.detail ?? response.statusText);
  }
  return (await response.json()) as T;
}
