import { useCallback, useEffect, useRef, useState } from 'react';

import { apiGet } from './client';

export interface ApiState<T> {
  data: T | null;
  error: Error | null;
  loading: boolean;
  reload: () => void;
  /** Локальное обновление после успешной записи, чтобы не перезапрашивать экран. */
  setData: (data: T) => void;
}

export function useApi<T>(path: string): ApiState<T> {
  const [state, setState] = useState<{ data: T | null; error: Error | null; loading: boolean }>({
    data: null,
    error: null,
    loading: true,
  });
  const [nonce, setNonce] = useState(0);
  const activePath = useRef(path);
  const reload = useCallback(() => setNonce((n) => n + 1), []);
  const setData = useCallback((data: T) => setState({ data, error: null, loading: false }), []);

  useEffect(() => {
    let cancelled = false;
    const pathChanged = activePath.current !== path;
    activePath.current = path;
    setState((previous) => ({ data: pathChanged ? null : previous.data, loading: true, error: null }));
    apiGet<T>(path).then(
      (data) => {
        if (!cancelled) setState({ data, error: null, loading: false });
      },
      (error: Error) => {
        // При ошибке обновления оставляем уже показанные данные на экране: владелец
        // может продолжить работу и повторить запрос, не проваливаясь в пустую заглушку.
        if (!cancelled) setState((previous) => ({ data: pathChanged ? null : previous.data, error, loading: false }));
      },
    );
    return () => {
      cancelled = true;
    };
  }, [path, nonce]);

  return { ...state, reload, setData };
}

export interface ActionState {
  running: boolean;
  error: Error | null;
  /** Возвращает undefined, если запрос не прошёл: ошибка уже в state.error. */
  run: <T>(task: () => Promise<T>) => Promise<T | undefined>;
  reset: () => void;
}

/** Запись на сервер: состояние «сохраняю» для кнопки и текст ошибки рядом с формой. */
export function useAction(): ActionState {
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const mounted = useRef(true);
  const inFlight = useRef(false);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const run = useCallback(async <T,>(task: () => Promise<T>): Promise<T | undefined> => {
    if (inFlight.current) return undefined;
    inFlight.current = true;
    setRunning(true);
    setError(null);
    try {
      const result = await task();
      return result;
    } catch (failure) {
      if (mounted.current) setError(failure as Error);
      return undefined;
    } finally {
      inFlight.current = false;
      if (mounted.current) setRunning(false);
    }
  }, []);

  return { running, error, run, reset: useCallback(() => setError(null), []) };
}

/** Обновляем оперативные экраны, когда пользователь возвращается в MAX. */
export function useReloadOnVisible(reload: () => void): void {
  useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState === 'visible') reload();
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => document.removeEventListener('visibilitychange', onVisible);
  }, [reload]);
}
