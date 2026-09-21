import { IconButton, Typography } from '@maxhub/max-ui';
import { type ReactNode, useCallback, useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';

import { useBackButton } from '../max/bridge';
import { Icon } from './Icon';

interface SheetProps {
  title: string;
  open: boolean;
  onClose: () => void;
  children: ReactNode;
}

/** Форма поверх экрана: в MAX UI 0.5.0 своего модального окна нет. */
export function Sheet({ title, open, onClose, children }: SheetProps) {
  const close = useCallback(() => onClose(), [onClose]);
  const dialog = useRef<HTMLDivElement>(null);
  useBackButton(open ? close : null);

  useEffect(() => {
    if (!open) return;
    const previouslyFocused = document.activeElement as HTMLElement | null;
    const previousOverflow = document.body.style.overflow;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        close();
        return;
      }
      if (event.key !== 'Tab') return;

      const focusable = Array.from(
        dialog.current?.querySelectorAll<HTMLElement>(
          'button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])',
        ) ?? [],
      );
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener('keydown', onKey);
    document.body.style.overflow = 'hidden';
    const frame = requestAnimationFrame(() => {
      // Не открываем экранную клавиатуру сразу: на телефоне это перекрывает
      // половину формы. Фокус остаётся внутри диалога и доступен с клавиатуры.
      dialog.current?.focus();
    });
    return () => {
      cancelAnimationFrame(frame);
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = previousOverflow;
      previouslyFocused?.focus();
    };
  }, [open, close]);

  if (!open) return null;

  const portalRoot = document.querySelector<HTMLElement>('.app-root') ?? document.body;

  return createPortal(
    <div className="sheet__backdrop" onClick={close}>
      <div
        ref={dialog}
        className="sheet"
        onClick={(event) => event.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
      >
        <div className="sheet__header">
          <Typography.Title variant="small-strong">{title}</Typography.Title>
          <IconButton size="small" variant="ghost" onClick={close} aria-label="Закрыть">
            <Icon name="close" />
          </IconButton>
        </div>
        <div className="sheet__body">{children}</div>
      </div>
    </div>,
    portalRoot,
  );
}
