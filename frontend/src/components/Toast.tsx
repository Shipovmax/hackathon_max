import { createContext, type ReactNode, useCallback, useContext, useEffect, useState } from 'react';

type Tone = 'ok' | 'bad';
interface Toast {
  id: number;
  text: string;
  tone: Tone;
}

interface ToastApi {
  show: (text: string, tone?: Tone) => void;
}

const ToastContext = createContext<ToastApi>({ show: () => {} });

/** Короткое подтверждение результата действия: «Сохранено», «График опубликован». */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [toast, setToast] = useState<Toast | null>(null);

  const show = useCallback((text: string, tone: Tone = 'ok') => {
    setToast({ id: Date.now(), text, tone });
  }, []);

  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(null), 2600);
    return () => clearTimeout(timer);
  }, [toast]);

  return (
    <ToastContext.Provider value={{ show }}>
      {children}
      {toast && (
        <div className={`toast toast--${toast.tone}`} role="status" key={toast.id}>
          {toast.text}
        </div>
      )}
    </ToastContext.Provider>
  );
}

export const useToast = (): ToastApi => useContext(ToastContext);
