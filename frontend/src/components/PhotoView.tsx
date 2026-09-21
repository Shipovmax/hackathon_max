import { useCallback, useEffect } from 'react';
import { createPortal } from 'react-dom';

import { useBackButton } from '../max/bridge';

interface PhotoViewProps {
  url: string | null;
  title: string;
  onClose: () => void;
}

/** Фото отметки во весь экран. Скачивание не нужно: владелец просто смотрит. */
export function PhotoView({ url, title, onClose }: PhotoViewProps) {
  const close = useCallback(() => onClose(), [onClose]);
  useBackButton(url ? close : null);

  useEffect(() => {
    if (!url) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') close();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [url, close]);

  if (!url) return null;

  return createPortal(
    <div className="photo" onClick={close} role="dialog" aria-label={title}>
      <img className="photo__image" src={url} alt={title} />
      <span className="photo__caption">{title}</span>
    </div>,
    document.body,
  );
}
