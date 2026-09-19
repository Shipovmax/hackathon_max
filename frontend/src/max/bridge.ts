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

export function useBackButton(onBack: (() => void) | null): void {
  useEffect(() => {
    const button = window.WebApp?.BackButton;
    if (!button || !onBack) return;
    button.show();
    button.onClick(onBack);
    return () => {
      button.offClick(onBack);
      button.hide();
    };
  }, [onBack]);
}
