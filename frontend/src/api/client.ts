import { getInitData } from '../max/bridge';
import { ApiError } from './errors';
import { mockRequest } from './mocks';

const USE_MOCKS = import.meta.env.VITE_USE_MOCKS === '1';
const REQUEST_TIMEOUT_MS = 15_000;

type Method = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';

async function fetchWithTimeout(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    return await fetch(input, { ...init, signal: controller.signal });
  } finally {
    window.clearTimeout(timer);
  }
}

async function request<T>(method: Method, path: string, body?: unknown): Promise<T> {
  if (USE_MOCKS) return mockRequest<T>(method, path, body);

  const headers: Record<string, string> = { 'X-Max-Init-Data': getInitData() };
  if (body !== undefined) headers['Content-Type'] = 'application/json';

  let response: Response;
  try {
    response = await fetchWithTimeout(`/api${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch (failure) {
    // Обрыв связи: фетч не дошёл до сервера, статуса нет.
    const timedOut = failure instanceof DOMException && failure.name === 'AbortError';
    throw new ApiError(0, timedOut ? 'timeout' : 'network', timedOut ? 'сервер не ответил вовремя' : 'нет связи с сервером');
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

/**
 * Фото отметки отдаёт наш бэкенд и проверяет подпись запуска, а тег <img>
 * заголовки не шлёт. Поэтому скачиваем сами и показываем из памяти.
 */
export async function apiBlobUrl(path: string): Promise<string> {
  if (USE_MOCKS) return mockRequest<string>('GET', path);

  let response: Response;
  try {
    response = await fetchWithTimeout(`/api${path}`, { headers: { 'X-Max-Init-Data': getInitData() } });
  } catch (failure) {
    const timedOut = failure instanceof DOMException && failure.name === 'AbortError';
    throw new ApiError(0, timedOut ? 'timeout' : 'network', timedOut ? 'сервер не ответил вовремя' : 'нет связи с сервером');
  }
  if (!response.ok) throw new ApiError(response.status, '', response.statusText);
  return URL.createObjectURL(await response.blob());
}
