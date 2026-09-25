import { useCallback, useEffect, useSyncExternalStore } from 'react';

import { watchColorScheme } from './bridge';

export type ThemeMode = 'auto' | 'light' | 'dark';
export type ColorScheme = 'light' | 'dark';

const KEY = 'theme-mode';

function readMode(): ThemeMode {
  try {
    const stored = localStorage.getItem(KEY);
    return stored === 'light' || stored === 'dark' ? stored : 'auto';
  } catch {
    return 'auto';
  }
}

function writeMode(mode: ThemeMode): void {
  try {
    if (mode === 'auto') localStorage.removeItem(KEY);
    else localStorage.setItem(KEY, mode);
  } catch {
  }
}

const systemScheme = (): ColorScheme =>
  window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';

let mode: ThemeMode = readMode();
let system: ColorScheme = systemScheme();
const listeners = new Set<() => void>();

const resolve = (): ColorScheme => (mode === 'auto' ? system : mode);
let snapshot: ColorScheme = resolve();

function emit(): void {
  const next = resolve();
  if (next === snapshot) return;
  snapshot = next;
  listeners.forEach((listener) => listener());
}

watchColorScheme((scheme) => {
  system = scheme;
  emit();
});

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useTheme() {
  const scheme = useSyncExternalStore(subscribe, () => snapshot);

  useEffect(() => {
    document.documentElement.dataset.theme = scheme;
  }, [scheme]);

  const toggle = useCallback(() => {
    mode = resolve() === 'dark' ? 'light' : 'dark';
    writeMode(mode);
    emit();
  }, []);

  return { scheme, toggle };
}
