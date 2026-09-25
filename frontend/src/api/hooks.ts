import { useCallback, useEffect, useRef, useState } from 'react';

import { apiGet } from './client';

export interface ApiState<T> {
  data: T | null;
  error: Error | null;
  loading: boolean;
  reload: () => void;
  setData: (data: T) => void;
}

export function useApi<T>(path: string): ApiState<T> {
  const [state, setState] = useState<{ data: T | null; error: Error | null; loading: boolean }>({
    data: null,
    error: null,
    loading: true,
  });
  const [nonce, setNonce] = useState(0);
  const reload = useCallback(() => setNonce((n) => n + 1), []);
  const setData = useCallback((data: T) => setState({ data, error: null, loading: false }), []);

  useEffect(() => {
    let cancelled = false;
    setState((previous) => ({ ...previous, loading: true, error: null }));
    apiGet<T>(path).then(
      (data) => {
        if (!cancelled) setState({ data, error: null, loading: false });
      },
      (error: Error) => {
        if (!cancelled) setState({ data: null, error, loading: false });
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
  run: <T>(task: () => Promise<T>) => Promise<T | undefined>;
  reset: () => void;
}

export function useAction(): ActionState {
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const run = useCallback(async <T,>(task: () => Promise<T>): Promise<T | undefined> => {
    setRunning(true);
    setError(null);
    try {
      const result = await task();
      if (mounted.current) setRunning(false);
      return result;
    } catch (failure) {
      if (mounted.current) {
        setError(failure as Error);
        setRunning(false);
      }
      return undefined;
    }
  }, []);

  return { running, error, run, reset: useCallback(() => setError(null), []) };
}
