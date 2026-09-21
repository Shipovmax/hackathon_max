import { useEffect } from 'react';

type WebAppPlatform = 'ios' | 'android' | 'desktop' | 'web';

interface MaxWebApp {
  initData: string;
  initDataUnsafe: { user?: { id: number; first_name?: string }; start_param?: string };
  platform: WebAppPlatform;
  version: string;
  BackButton: {
    show(): void;
    hide(): void;
    onClick(callback: () => void): void;
    offClick(callback: () => void): void;
  };
  openMaxLink(url: string): void;
}

declare global {
  interface Window {
    WebApp?: MaxWebApp;
  }
}

export const getInitData = (): string => window.WebApp?.initData ?? '';
export const getPlatform = (): WebAppPlatform => window.WebApp?.platform ?? 'web';
export const isInsideMax = (): boolean => Boolean(window.WebApp?.initData);

// Обработчики «Назад» складываются в стопку: сработает верхний. Так открытая форма
// закрывается по «Назад», а не уводит пользователя с экрана.
const handlers: (() => void)[] = [];
const dispatch = () => handlers[handlers.length - 1]?.();
let attached = false;

function sync(): void {
  const button = window.WebApp?.BackButton;
  if (!button) return;
  if (handlers.length > 0) {
    if (!attached) {
      button.onClick(dispatch);
      attached = true;
    }
    button.show();
  } else {
    button.hide();
  }
}

export function useBackButton(onBack: (() => void) | null): void {
  useEffect(() => {
    if (!onBack) return;
    handlers.push(onBack);
    sync();
    return () => {
      const index = handlers.lastIndexOf(onBack);
      if (index >= 0) handlers.splice(index, 1);
      sync();
    };
  }, [onBack]);
}

/** Тема MAX меняется на ходу, приложение должно перекрашиваться вместе с ней. */
export function watchColorScheme(onChange: (scheme: 'light' | 'dark') => void): () => void {
  const media = window.matchMedia('(prefers-color-scheme: dark)');
  const listener = () => onChange(media.matches ? 'dark' : 'light');
  media.addEventListener('change', listener);
  return () => media.removeEventListener('change', listener);
}
