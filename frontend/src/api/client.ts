import { getInitData } from '../max/bridge';
import { ApiError } from './errors';
import { mockRequest } from './mocks';

const USE_MOCKS = import.meta.env.VITE_USE_MOCKS === '1';

type Method = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';

async function request<T>(method: Method, path: string, body?: unknown): Promise<T> {
  if (USE_MOCKS) return mockRequest<T>(method, path, body);

  const headers: Record<string, string> = { 'X-Max-Init-Data': getInitData() };
  if (body !== undefined) headers['Content-Type'] = 'application/json';

  let response: Response;
  try {
    response = await fetch(`/api${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, 'network', 'нет связи с сервером');
  }

  if (!response.ok) {
    const payload = (await response.json().catch(() => ({}))) as { code?: string; detail?: string };
    throw new ApiError(response.status, payload.code ?? '', payload.detail ?? response.statusText);
  }
  if (response.status === 204) return null as T;
  return (await response.json()) as T;
}

export const apiGet = <T>(path: string) => request<T>('GET', path);
export const apiPost = <T>(path: string, body?: unknown) => request<T>('POST', path, body ?? {});
export const apiPut = <T>(path: string, body: unknown) => request<T>('PUT', path, body);
export const apiPatch = <T>(path: string, body: unknown) => request<T>('PATCH', path, body);
export const apiDelete = <T>(path: string) => request<T>('DELETE', path);

export async function apiBlobUrl(path: string): Promise<string> {
  if (USE_MOCKS) return mockRequest<string>('GET', path);

  let response: Response;
  try {
    response = await fetch(`/api${path}`, { headers: { 'X-Max-Init-Data': getInitData() } });
  } catch {
    throw new ApiError(0, 'network', 'нет связи с сервером');
  }
  if (!response.ok) throw new ApiError(response.status, '', response.statusText);
  return URL.createObjectURL(await response.blob());
}
