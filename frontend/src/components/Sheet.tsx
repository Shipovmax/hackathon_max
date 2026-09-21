import { IconButton, Typography } from '@maxhub/max-ui';
import { type ReactNode, useCallback, useEffect } from 'react';
import { createPortal } from 'react-dom';

import { useBackButton } from '../max/bridge';

interface SheetProps {
  title: string;
  open: boolean;
  onClose: () => void;
  children: ReactNode;
}

/** Форма поверх экрана: в MAX UI 0.5.0 своего модального окна нет. */
export function Sheet({ title, open, onClose, children }: SheetProps) {
  const close = useCallback(() => onClose(), [onClose]);
  useBackButton(open ? close : null);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') close();
    };
    document.addEventListener('keydown', onKey);
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = '';
    };
  }, [open, close]);

  if (!open) return null;

  return createPortal(
    <div className="sheet__backdrop" onClick={close}>
      <div className="sheet" onClick={(event) => event.stopPropagation()} role="dialog" aria-label={title}>
        <div className="sheet__header">
          <Typography.Title variant="small-strong">{title}</Typography.Title>
          <IconButton size="small" variant="ghost" onClick={close} aria-label="Закрыть">
            ✕
          </IconButton>
        </div>
        <div className="sheet__body">{children}</div>
      </div>
    </div>,
    document.body,
  );
}
